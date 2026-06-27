/*********************************************************************************************************************
 * @file    uart_dma.c
 * @brief   SCB UART + DW DMA implementation.
 *
 * Code reused / adapted from:
 *   - SDL example: project/code/dw_with_scb_uart/main_cm7_0.c
 *   - SDL PDMA driver: libraries/sdk/common/src/drivers/dma/cy_pdma.c/.h
 *   - SDL SCB UART driver: libraries/sdk/common/src/drivers/scb/cy_scb_uart.c/.h
 ********************************************************************************************************************/

#include "uart_dma.h"
#include "image_protocol.h"

#include "cy_project.h"
#include "cy_device_headers.h"
#include "zf_common_interrupt.h"

/* ------------------------------------------------------------------------------------------------------------------ */
/* Configuration constants (from SDL DW_with_SCB_UART example)                                                        */
/* ------------------------------------------------------------------------------------------------------------------ */
#define UART_TX_FIFO_LEVEL          (16ul)
#define UART_OVERSAMPLING           (8ul)
#define UART_BAUDRATE               (2000000ul)     /* 2 Mbps with 80 MHz peri clock -> exact divider 5 */
#define UART_SOURCE_FREQ            (80000000ul)    /* CY_INITIAL_TARGET_PERI_FREQ for non-PSVP board */

#define UART_DW_CHANNEL             (22u)
#define UART_DW_INTR                (cpuss_interrupts_dw1_22_IRQn)
#define UART_TX_TO_DMA_TRIG         (TRIG_IN_1TO1_2_SCB_TX_TO_PDMA13)

/* ------------------------------------------------------------------------------------------------------------------ */
/* SCB UART configuration (copied from SDL DW_with_SCB_UART example)                                                  */
/* ------------------------------------------------------------------------------------------------------------------ */
static cy_stc_scb_uart_context_t    s_uart_context;
static const cy_stc_scb_uart_config_t s_uart_config =
{
    .uartMode                   = CY_SCB_UART_STANDARD,
    .oversample                 = UART_OVERSAMPLING,
    .dataWidth                  = 8ul,
    .enableMsbFirst             = false,
    .stopBits                   = CY_SCB_UART_STOP_BITS_1,
    .parity                     = CY_SCB_UART_PARITY_NONE,
    .enableInputFilter          = false,
    .dropOnParityError          = false,
    .dropOnFrameError           = false,
    .enableMutliProcessorMode   = false,
    .receiverAddress            = 0ul,
    .receiverAddressMask        = 0ul,
    .acceptAddrInFifo           = false,
    .irdaInvertRx               = false,
    .irdaEnableLowPowerReceiver = false,
    .smartCardRetryOnNack       = false,
    .enableCts                  = false,
    .ctsPolarity                = CY_SCB_UART_ACTIVE_LOW,
    .rtsRxFifoLevel             = 0ul,
    .rtsPolarity                = CY_SCB_UART_ACTIVE_LOW,
    .breakWidth                 = 0ul,
    .rxFifoTriggerLevel         = 0ul,
    .rxFifoIntEnableMask        = 0ul,
    .txFifoTriggerLevel         = UART_TX_FIFO_LEVEL,
    .txFifoIntEnableMask        = 0ul
};

/* ------------------------------------------------------------------------------------------------------------------ */
/* DMA descriptor and channel config (copied and adapted from SDL DW_with_SCB_UART example)                           */
/* ------------------------------------------------------------------------------------------------------------------ */
static cy_stc_pdma_descr_t          s_uart_tx_descr;
static const cy_stc_pdma_chnl_config_t s_uart_tx_chnl_config =
{
    .PDMA_Descriptor = &s_uart_tx_descr,
    .preemptable     = 0ul,
    .priority        = 0ul,
    .enable          = 1ul,
};

/* The descriptor is updated at run time with the frame buffer address. Y-count is fixed by padding. */
static cy_stc_pdma_descr_config_t s_uart_tx_descr_config =
{
    .deact          = 0ul,
    .intrType       = CY_PDMA_INTR_DESCR_CMPLT,
    .trigoutType    = CY_PDMA_TRIGOUT_DESCR_CMPLT,
    .chStateAtCmplt = CY_PDMA_CH_DISABLED,
    .triginType     = CY_PDMA_TRIGIN_XLOOP,
    .dataSize       = CY_PDMA_BYTE,
    .srcTxfrSize    = 0ul,      /* same as dataSize */
    .destTxfrSize   = 1ul,      /* 32-bit TX FIFO write register */
    .descrType      = CY_PDMA_2D_TRANSFER,
    .srcAddr        = NULL,     /* updated per frame */
    .destAddr       = (void *)&CY_USB_SCB_UART_TYPE->unTX_FIFO_WR.u32Register,
    .srcXincr       = 1ul,
    .destXincr      = 0ul,
    .xCount         = IMAGE_DMA_XFER_SIZE,
    .srcYincr       = IMAGE_DMA_XFER_SIZE,
    .destYincr      = 0ul,
    .yCount         = IMAGE_DMA_Y_COUNT,
    .descrNext      = &s_uart_tx_descr
};

/* ------------------------------------------------------------------------------------------------------------------ */
/* Local variables                                                                                                    */
/* ------------------------------------------------------------------------------------------------------------------ */
static volatile bool s_tx_busy = false;

/* CPUIntIdx4_IRQn is chosen because CPUIntIdx2 is used by the ZhuFei PIT driver,
 * CPUIntIdx3 by the ZhuFei UART driver, and CPUIntIdx1 by our CRC DMA ISR. */
static const cy_stc_sysint_irq_t s_uart_tx_irq_cfg =
{
    .sysIntSrc = UART_DW_INTR,
    .intIdx    = CPUIntIdx4_IRQn,
    .isEnabled = true,
};

/* ISR wrapper defined in cm7_0_isr.c. */
extern void dw1_ch22_isr(void);

/* ------------------------------------------------------------------------------------------------------------------ */
/* Local functions                                                                                                    */
/* ------------------------------------------------------------------------------------------------------------------ */
/**
 * @brief Initialize the SCB3 UART pins, peripheral and clock divider.
 *
 * Reused from the SDL DW_with_SCB_UART example; only the baud rate parameter is changed.
 */
static void uart_hw_init(void)
{
    cy_stc_gpio_pin_config_t stc_port_pin_cfg_uart = {0};

    /* RX pin: high-Z input. */
    stc_port_pin_cfg_uart.driveMode = CY_GPIO_DM_HIGHZ;
    stc_port_pin_cfg_uart.hsiom     = CY_USB_SCB_UART_RX_PIN_MUX;
    Cy_GPIO_Pin_Init(CY_USB_SCB_UART_RX_PORT, CY_USB_SCB_UART_RX_PIN, &stc_port_pin_cfg_uart);

    /* TX pin: strong drive, input disabled. */
    stc_port_pin_cfg_uart.driveMode = CY_GPIO_DM_STRONG_IN_OFF;
    stc_port_pin_cfg_uart.hsiom     = CY_USB_SCB_UART_TX_PIN_MUX;
    Cy_GPIO_Pin_Init(CY_USB_SCB_UART_TX_PORT, CY_USB_SCB_UART_TX_PIN, &stc_port_pin_cfg_uart);

    /* SCB-UART initialization. */
    Cy_SCB_UART_DeInit(CY_USB_SCB_UART_TYPE);
    Cy_SCB_UART_Init(CY_USB_SCB_UART_TYPE, &s_uart_config, &s_uart_context);
    Cy_SCB_UART_Enable(CY_USB_SCB_UART_TYPE);

    /* Clock configuration: assign and configure a 24.5-bit fractional divider. */
    Cy_SysClk_PeriphAssignDivider(CY_USB_SCB_UART_PCLK, CY_SYSCLK_DIV_24_5_BIT, 0u);
    {
        uint64_t targetFreq     = (uint64_t)UART_OVERSAMPLING * (uint64_t)UART_BAUDRATE;
        uint64_t sourceFreq_fp5 = ((uint64_t)UART_SOURCE_FREQ << 5ull);
        uint32_t divSetting_fp5 = (uint32_t)(sourceFreq_fp5 / targetFreq);
        Cy_SysClk_PeriphSetFracDivider(Cy_SysClk_GetClockGroup(CY_USB_SCB_UART_PCLK),
                                       CY_SYSCLK_DIV_24_5_BIT,
                                       0u,
                                       ((divSetting_fp5 & 0x1FFFFFE0ul) >> 5ul),
                                       (divSetting_fp5 & 0x0000001Ful));
    }
    Cy_SysClk_PeriphEnableDivider(Cy_SysClk_GetClockGroup(CY_USB_SCB_UART_PCLK), CY_SYSCLK_DIV_24_5_BIT, 0u);
}

/* ------------------------------------------------------------------------------------------------------------------ */
/* Public functions                                                                                                   */
/* ------------------------------------------------------------------------------------------------------------------ */
void UART_DMA_Init(void)
{
    /* Initialize SCB3 UART hardware (reused from SDL example). */
    uart_hw_init();

    /* Initialize DW1 channel 22 for UART TX (reused from SDL example). */
    Cy_PDMA_Disable(DW1);
    Cy_PDMA_Chnl_DeInit(DW1, UART_DW_CHANNEL);
    Cy_PDMA_Descr_Init(&s_uart_tx_descr, &s_uart_tx_descr_config);
    Cy_PDMA_Chnl_Init(DW1, UART_DW_CHANNEL, &s_uart_tx_chnl_config);
    Cy_PDMA_Chnl_SetInterruptMask(DW1, UART_DW_CHANNEL);
    Cy_PDMA_Enable(DW1);

    /* Connect SCB3 TX FIFO trigger to DW1 channel 22 (reused from SDL example). */
    Cy_TrigMux_Connect1To1(UART_TX_TO_DMA_TRIG, 0ul, TRIGGER_TYPE_LEVEL, 0ul);

    /* Register the UART TX DMA ISR wrapper (defined in cm7_0_isr.c) using the ZhuFei interrupt helper. */
    interrupt_init(&s_uart_tx_irq_cfg, (cy_systemIntr_Handler)dw1_ch22_isr, 7u);
}

void UART_DMA_SetSourceBuffer(const uint8_t *src)
{
    if (src != NULL)
    {
        s_uart_tx_descr.u32PDMA_DESCR_SRC = (uint32_t)src;
    }
}

bool UART_DMA_SendFrame(void)
{
    if (s_tx_busy)
    {
        return false;
    }

    s_tx_busy = true;

    /* Make sure the descriptor pointer is loaded; source is updated via SetSourceBuffer. */
    Cy_PDMA_Chnl_SetDescr(DW1, UART_DW_CHANNEL, &s_uart_tx_descr);

    /* Enable channel. The UART TX FIFO level trigger will pace the 2D transfer. */
    Cy_PDMA_Chnl_Enable(DW1, UART_DW_CHANNEL);

    return true;
}

bool UART_DMA_IsBusy(void)
{
    return s_tx_busy;
}

void UART_DMA_Callback(void)
{
    uint32_t masked;

    masked = Cy_PDMA_Chnl_GetInterruptStatusMasked(DW1, UART_DW_CHANNEL);
    if ((masked & CY_PDMA_INTRCAUSE_COMPLETION) != 0ul)
    {
        Cy_PDMA_Chnl_ClearInterrupt(DW1, UART_DW_CHANNEL);
        s_tx_busy = false;
    }
    else
    {
        /* Unexpected interrupt cause: clear it and release the bus flag to avoid lockup. */
        Cy_PDMA_Chnl_ClearInterrupt(DW1, UART_DW_CHANNEL);
        s_tx_busy = false;
    }
}
