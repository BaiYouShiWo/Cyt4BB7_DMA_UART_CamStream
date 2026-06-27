/*********************************************************************************************************************
 * @file    image_protocol.h
 * @brief   Image transmission protocol definitions for CYT4BB7 camera stream.
 *
 * Frame format (little-endian, 22580 bytes without padding):
 *   [0:1]   Header              0xAA 0x55
 *   [2]     Protocol Version    0x01
 *   [3:6]   Frame Counter       uint32
 *   [7:8]   Width               uint16  (188)
 *   [9:10]  Height              uint16  (120)
 *   [11]    Pixel Format        0x01    (Grayscale)
 *   [12:15] Payload Length      uint32  (22560)
 *   [16:22575] Image Payload    22560 bytes
 *   [22576:22577] CRC16         CRC-16/CCITT-FALSE
 *   [22578:22579] Tail          0x55 0xAA
 *
 * CRC covers bytes [2 .. 22575] (protocol fields + image payload).
 * Header and tail are NOT included in CRC.
 *
 * The frame buffer is padded to a multiple of IMAGE_DMA_XFER_SIZE so that the
 * DW 2D DMA descriptor used by the SDL UART example can transfer it in one shot.
 ********************************************************************************************************************/

#ifndef IMAGE_PROTOCOL_H
#define IMAGE_PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------------------------------------------------------ */
/* Frame constants                                                                                                    */
/* ------------------------------------------------------------------------------------------------------------------ */
#define IMAGE_HEADER_0              (0xAAu)
#define IMAGE_HEADER_1              (0x55u)
#define IMAGE_TAIL_0                (0x55u)
#define IMAGE_TAIL_1                (0xAAu)

#define IMAGE_PROTOCOL_VERSION      (0x01u)
#define IMAGE_PIXEL_FORMAT_GRAY     (0x01u)

#define IMAGE_WIDTH                 (188u)
#define IMAGE_HEIGHT                (120u)
#define IMAGE_PAYLOAD_SIZE          ((uint32_t)(IMAGE_WIDTH * IMAGE_HEIGHT))   /* 22560 */

#define IMAGE_METADATA_SIZE         (14u)   /* version + counter + w + h + format + length */
#define IMAGE_CRC_SIZE              (2u)
#define IMAGE_HEADER_SIZE           (2u)
#define IMAGE_TAIL_SIZE             (2u)

#define IMAGE_FRAME_UNPADDED_SIZE   ((uint32_t)(IMAGE_HEADER_SIZE + \
                                                 IMAGE_METADATA_SIZE + \
                                                 IMAGE_PAYLOAD_SIZE + \
                                                 IMAGE_CRC_SIZE + \
                                                 IMAGE_TAIL_SIZE))   /* 22580 */

/* DMA transfer chunk size. The SCB TX FIFO is 128 bytes deep and the trigger level
 * is 16; when the trigger fires the FIFO has at most 16 entries, leaving >= 112
 * empty slots. The DW 2D descriptor uses CY_PDMA_TRIGIN_XLOOP with xCount = 112 so
 * that each trigger refills the FIFO without overflow, while yCount stays inside
 * the 8-bit descriptor field. */
#define IMAGE_DMA_XFER_SIZE         (112u)
#define IMAGE_FRAME_PADDED_SIZE     (((IMAGE_FRAME_UNPADDED_SIZE + IMAGE_DMA_XFER_SIZE - 1u) / IMAGE_DMA_XFER_SIZE) * IMAGE_DMA_XFER_SIZE)
#define IMAGE_DMA_Y_COUNT           (IMAGE_FRAME_PADDED_SIZE / IMAGE_DMA_XFER_SIZE)

/* Offset of each field inside the contiguous frame buffer */
#define IMAGE_OFF_HEADER            (0u)
#define IMAGE_OFF_VERSION           (IMAGE_HEADER_SIZE)
#define IMAGE_OFF_FRAME_COUNTER     (IMAGE_OFF_VERSION + 1u)
#define IMAGE_OFF_WIDTH             (IMAGE_OFF_FRAME_COUNTER + 4u)
#define IMAGE_OFF_HEIGHT            (IMAGE_OFF_WIDTH + 2u)
#define IMAGE_OFF_PIXEL_FORMAT      (IMAGE_OFF_HEIGHT + 2u)
#define IMAGE_OFF_PAYLOAD_LENGTH    (IMAGE_OFF_PIXEL_FORMAT + 1u)
#define IMAGE_OFF_PAYLOAD           (IMAGE_HEADER_SIZE + IMAGE_METADATA_SIZE)
#define IMAGE_OFF_CRC               (IMAGE_OFF_PAYLOAD + IMAGE_PAYLOAD_SIZE)
#define IMAGE_OFF_TAIL              (IMAGE_OFF_CRC + IMAGE_CRC_SIZE)

/* CRC covers metadata + payload, starting right after the header */
#define IMAGE_CRC_START_OFFSET      (IMAGE_HEADER_SIZE)
#define IMAGE_CRC_LENGTH            ((uint32_t)(IMAGE_METADATA_SIZE + IMAGE_PAYLOAD_SIZE))

/* ------------------------------------------------------------------------------------------------------------------ */
/* Types                                                                                                              */
/* ------------------------------------------------------------------------------------------------------------------ */
typedef struct
{
    uint8_t  version;
    uint32_t frame_counter;
    uint16_t width;
    uint16_t height;
    uint8_t  pixel_format;
    uint32_t payload_length;
} image_metadata_t;

/* ------------------------------------------------------------------------------------------------------------------ */
/* API                                                                                                                */
/* ------------------------------------------------------------------------------------------------------------------ */

/**
 * @brief Pack metadata fields into a contiguous byte array (little-endian).
 * @param meta      Source metadata structure.
 * @param dst       Destination buffer, must be at least IMAGE_METADATA_SIZE bytes.
 */
void ImageProtocol_PackMetadata(const image_metadata_t *meta, uint8_t *dst);

/**
 * @brief Build the protocol wrapper (header + metadata + CRC + tail) into the frame buffer.
 * @param frame_buf     Frame buffer of IMAGE_FRAME_PADDED_SIZE bytes.
 * @param meta          Metadata to write.
 * @param crc16         CRC16 value to store.
 */
void ImageProtocol_BuildWrapper(uint8_t *frame_buf, const image_metadata_t *meta, uint16_t crc16);

/**
 * @brief Return a pointer to the payload area inside the frame buffer.
 */
static inline uint8_t *ImageProtocol_GetPayloadPtr(uint8_t *frame_buf)
{
    return &frame_buf[IMAGE_OFF_PAYLOAD];
}

/**
 * @brief Return the total number of valid bytes in a frame (excluding padding).
 */
static inline uint32_t ImageProtocol_GetFrameSize(void)
{
    return IMAGE_FRAME_UNPADDED_SIZE;
}

/**
 * @brief Return the padded frame buffer size used by DMA.
 */
static inline uint32_t ImageProtocol_GetPaddedFrameSize(void)
{
    return IMAGE_FRAME_PADDED_SIZE;
}

#ifdef __cplusplus
}
#endif

#endif /* IMAGE_PROTOCOL_H */
