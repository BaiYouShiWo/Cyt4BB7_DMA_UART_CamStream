/*********************************************************************************************************************
 * @file    crc_hw.c
 * @brief   Hardware CRC16 using the PDMA CRC engine.
 *
 * Channel: DW1 channel 7 (same index as the SDL CRC example).
 * Trigger: software trigger on TRIG_OUT_MUX_2_PDMA1_TR_IN7.
 *
 * Code reused / adapted from:
 *   - SDL example: project/code/crc/main_cm7_0.c
 *   - SDL PDMA driver: libraries/sdk/common/src/drivers/dma/cy_pdma.c/.h
 ********************************************************************************************************************/

#include "crc_hw.h"

#include "cy_project.h"
#include "cy_device_headers.h"
#include "zf_common_interrupt.h"

/* ------------------------------------------------------------------------------------------------------------------ */
/* CRC channel configuration (reused from SDL CRC example)                                                            */
/* ------------------------------------------------------------------------------------------------------------------ */
#define CRC_DW_CHANNEL          (7u)
#define CRC_DW_INTR             (cpuss_interrupts_dw1_7_IRQn)
#define CRC_DW_SW_TRIG          (TRIG_OUT_MUX_2_PDMA1_TR_IN7)

/* PDMA CRC engine can transfer at most 256 bytes in one X-loop (8-bit X_COUNT). */
#define CRC_MAX_CHUNK_SIZE      (256u)

/* CRC-16/CCITT-FALSE configuration mapped to the 32-bit PDMA CRC registers. */
#define CRC16_POLY              (0x10210000u)   /* 0x1021 placed in upper 16 bits */
#define CRC16_INIT_SEED         (0xFFFF0000u)   /* 0xFFFF placed in upper 16 bits */
#define CRC16_REM_XOR           (0x00000000u)
#define CRC16_DATA_XOR          (0x00u)

/* Polling timeout for one chunk. At 80 MHz system clock this is >> the DMA time. */
#define CRC_CHUNK_TIMEOUT       (100000u)

/* ------------------------------------------------------------------------------------------------------------------ */
/* Local variables                                                                                                    */
/* ------------------------------------------------------------------------------------------------------------------ */
static cy_stc_pdma_descr_t  s_crc_descr;
static volatile bool        s_crc_done = false;
static uint32_t             s_crc_dummy_dst = 0ul;

/* CPUIntIdx1_IRQn is chosen because CPUIntIdx2 is used by the ZhuFei PIT driver and
 * CPUIntIdx3 by the ZhuFei UART driver. */
static const cy_stc_sysint_irq_t s_crc_irq_cfg =
{
    .sysIntSrc = CRC_DW_INTR,
    .intIdx    = CPUIntIdx1_IRQn,
    .isEnabled = true,
};

/* ISR wrapper defined in cm7_0_isr.c. */
extern void dw1_ch7_isr(void);

static const cy_stc_pdma_chnl_config_t s_crc_chnl_config =
{
    .PDMA_Descriptor = &s_crc_descr,
    .preemptable     = 0ul,
    .priority        = 0ul,
    .enable          = 1ul,
};

static cy_stc_pdma_descr_config_t s_crc_descr_config =
{
    .deact          = 0ul,
    .intrType       = CY_PDMA_INTR_DESCR_CMPLT,
    .trigoutType    = CY_PDMA_TRIGOUT_DESCR_CMPLT,
    .chStateAtCmplt = CY_PDMA_CH_DISABLED,
    .triginType     = CY_PDMA_TRIGIN_DESCR,
    .dataSize       = CY_PDMA_BYTE,
    .srcTxfrSize    = 0ul,              /* same as dataSize */
    .destTxfrSize   = 1ul,              /* 32-bit CRC result */
    .descrType      = CY_PDMA_CRC_TRANSFER,
    .srcAddr        = NULL,             /* updated per chunk */
    .destAddr       = &s_crc_dummy_dst, /* result goes to CRC_REM_RESULT register; dest is dummy */
    .srcXincr       = 1ul,
    .xCount         = 0u,               /* updated per chunk */
    .descrNext      = &s_crc_descr      /* self-loop (unused because chStateAtCmplt disables channel) */
};

static const cy_stc_pdma_crc_config_t s_crc16_config =
{
    .data_reverse = 0ul,
    .rem_reverse  = 0ul,
    .data_xor     = CRC16_DATA_XOR,
    .polynomial   = CRC16_POLY,
    .lfsr32       = CRC16_INIT_SEED,
    .rem_xor      = CRC16_REM_XOR,
};

/* ------------------------------------------------------------------------------------------------------------------ */
/* Local helpers                                                                                                      */
/* ------------------------------------------------------------------------------------------------------------------ */
static bool crc16_run_chunk(const uint8_t *data, uint32_t length, uint16_t seed, uint16_t *crc_out)
{
    uint32_t timeout;
    uint32_t raw_result;

    if ((data == NULL) || (length == 0u) || (length > CRC_MAX_CHUNK_SIZE) || (crc_out == NULL))
    {
        return false;
    }

    /* Configure the CRC engine with the current seed. */
    cy_stc_pdma_crc_config_t crc_cfg = s_crc16_config;
    crc_cfg.lfsr32 = ((uint32_t)seed) << 16u;
    Cy_PDMA_CRC_Config(DW1, &crc_cfg);

    /* Update descriptor for this chunk. */
    s_crc_descr_config.srcAddr = (void *)data;
    s_crc_descr_config.xCount  = length;
    Cy_PDMA_Descr_Init(&s_crc_descr, &s_crc_descr_config);

    s_crc_done = false;

    /* Enable channel and trigger the CRC transfer. */
    Cy_PDMA_Chnl_Enable(DW1, CRC_DW_CHANNEL);
    Cy_TrigMux_SwTrigger(CRC_DW_SW_TRIG, TRIGGER_TYPE_EDGE, 1ul);

    /* Wait for completion with timeout (same polling pattern as SDL CRC example). */
    timeout = CRC_CHUNK_TIMEOUT;
    while ((s_crc_done == false) && (timeout != 0u))
    {
        timeout--;
    }

    if (s_crc_done == false)
    {
        return false;     /* timeout */
    }

    /* Result is in the upper 16 bits of the 32-bit remainder register. */
    raw_result = Cy_PDMA_GetCrcRemainderResult(DW1);
    *crc_out = (uint16_t)((raw_result >> 16u) & 0xFFFFu);
    return true;
}

/* ------------------------------------------------------------------------------------------------------------------ */
/* Public functions                                                                                                   */
/* ------------------------------------------------------------------------------------------------------------------ */
void CRC16_Init(void)
{
    /* Reuse the exact initialization sequence from the SDL CRC example. */
    Cy_PDMA_Disable(DW1);
    Cy_PDMA_Chnl_DeInit(DW1, CRC_DW_CHANNEL);
    Cy_PDMA_Descr_Init(&s_crc_descr, &s_crc_descr_config);
    Cy_PDMA_Chnl_Init(DW1, CRC_DW_CHANNEL, &s_crc_chnl_config);
    Cy_PDMA_Chnl_SetInterruptMask(DW1, CRC_DW_CHANNEL);
    Cy_PDMA_Enable(DW1);

    /* Register the CRC DMA ISR wrapper (defined in cm7_0_isr.c) using the ZhuFei interrupt helper. */
    interrupt_init(&s_crc_irq_cfg, (cy_systemIntr_Handler)dw1_ch7_isr, 7u);
}

bool CRC16_Calculate(const uint8_t *data, uint32_t length, uint16_t seed, uint16_t *crc_out)
{
    uint32_t remaining;
    uint32_t chunk;
    uint16_t current_crc = seed;
    const uint8_t *p;

    if (crc_out == NULL)
    {
        return false;
    }

    if ((data == NULL) && (length != 0u))
    {
        return false;
    }

    if (length == 0u)
    {
        *crc_out = seed;
        return true;
    }

    remaining = length;
    p = data;

    while (remaining > 0u)
    {
        chunk = (remaining > CRC_MAX_CHUNK_SIZE) ? CRC_MAX_CHUNK_SIZE : remaining;
        if (!crc16_run_chunk(p, chunk, current_crc, &current_crc))
        {
            /* Timeout or invalid chunk; abort. */
            return false;
        }

        p += chunk;
        remaining -= chunk;
    }

    *crc_out = current_crc;
    return true;
}

/* ------------------------------------------------------------------------------------------------------------------ */
/* ISR callback (called from cm7_0_isr.c dw1_ch7_isr)                                                                 */
/* ------------------------------------------------------------------------------------------------------------------ */
void CRC16_IRQHandler(void)
{
    uint32_t masked;

    masked = Cy_PDMA_Chnl_GetInterruptStatusMasked(DW1, CRC_DW_CHANNEL);
    if ((masked & CY_PDMA_INTRCAUSE_COMPLETION) != 0ul)
    {
        Cy_PDMA_Chnl_ClearInterrupt(DW1, CRC_DW_CHANNEL);
        s_crc_done = true;
    }
    else
    {
        /* Unexpected interrupt cause: clear it. */
        Cy_PDMA_Chnl_ClearInterrupt(DW1, CRC_DW_CHANNEL);
    }
}
