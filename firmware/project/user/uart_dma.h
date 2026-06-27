/*********************************************************************************************************************
 * @file    uart_dma.h
 * @brief   SCB UART + DW DMA driver for high-speed image transmission.
 *
 * Peripheral: SCB3 (USB-UART on the base board).
 * DMA:        DW1 channel 22 (TRIG_IN_1TO1_2_SCB_TX_TO_PDMA13).
 *
 * Initialization is reused from the SDL DW_with_SCB_UART example.
 ********************************************************************************************************************/

#ifndef UART_DMA_H
#define UART_DMA_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize SCB3 UART and DW1 channel 22 for DMA-driven TX.
 *
 * Reuses the initialization sequence from the SDL DW_with_SCB_UART example:
 *   GPIO init -> SCB UART init/enable -> clock divider -> DW1 disable/deinit ->
 *   descriptor init -> channel init -> interrupt mask -> DW1 enable -> trigger mux.
 */
void UART_DMA_Init(void);

/**
 * @brief Set the source frame buffer for the next DMA transfer.
 *
 * The buffer must be at least IMAGE_FRAME_PADDED_SIZE bytes and already contain
 * the complete frame (header, metadata, image, CRC, tail, padding).
 *
 * @param src   Pointer to the frame buffer.
 */
void UART_DMA_SetSourceBuffer(const uint8_t *src);

/**
 * @brief Start the UART TX DMA transfer.
 *
 * @return true if the transfer was started, false if a transfer is already active.
 */
bool UART_DMA_SendFrame(void);

/**
 * @brief Return true if a frame transfer is currently in progress.
 */
bool UART_DMA_IsBusy(void);

/**
 * @brief ISR callback for DW1 channel 22.
 *
 * Called from cm7_0_isr.c. Do not call from application code.
 */
void UART_DMA_Callback(void);

#ifdef __cplusplus
}
#endif

#endif /* UART_DMA_H */
