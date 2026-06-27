/*********************************************************************************************************************
 * @file    image_sender.h
 * @brief   High-level image sender with frame protocol, hardware CRC and DMA state machine.
 *
 * The sender builds one complete frame in a local padded buffer and triggers a
 * single DW DMA transfer to the SCB UART TX FIFO. The camera image is copied
 * once into the frame buffer so that the DMA can transmit the whole frame with
 * the exact SDL 2D-transfer descriptor pattern used in the examples.
 *
 * Public APIs:
 *   ImageSender_Init()
 *   ImageSender_IsBusy()
 *   ImageSender_SendFrame(uint8_t *image)
 *   ImageSender_DmaDoneCallback()   -- called by UART_DMA_Callback() ISR only
 ********************************************************************************************************************/

#ifndef IMAGE_SENDER_H
#define IMAGE_SENDER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize the image sender (CRC + UART DMA).
 */
void ImageSender_Init(void);

/**
 * @brief Return true if a frame is currently being transmitted.
 */
bool ImageSender_IsBusy(void);

/**
 * @brief Start sending one camera frame.
 *
 * The function is non-blocking: it copies the image, computes the CRC, builds
 * the protocol wrapper and starts the UART DMA, then returns. If the sender is
 * already busy the frame is dropped and the function returns false.
 *
 * @param image     Pointer to the 188x120 grayscale image buffer.
 * @return true     Frame accepted for transmission.
 * @return false    Busy or invalid parameter.
 */
bool ImageSender_SendFrame(uint8_t *image);

/**
 * @brief ISR callback invoked when the UART DMA finishes a frame.
 *
 * Do not call from application code.
 */
void ImageSender_DmaDoneCallback(void);

/**
 * @brief Read transmission statistics.
 *
 * @param frames_sent     Optional output for sent frame counter.
 * @param frames_dropped  Optional output for dropped frame counter.
 */
void ImageSender_GetStats(uint32_t *frames_sent, uint32_t *frames_dropped);

#ifdef __cplusplus
}
#endif

#endif /* IMAGE_SENDER_H */
