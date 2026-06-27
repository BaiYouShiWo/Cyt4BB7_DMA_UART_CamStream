/*********************************************************************************************************************
 * @file    image_protocol.c
 * @brief   Image frame protocol packing helpers.
 ********************************************************************************************************************/

#include "image_protocol.h"

/* ------------------------------------------------------------------------------------------------------------------ */
/* Local helpers for little-endian packing                                                                            */
/* ------------------------------------------------------------------------------------------------------------------ */
static inline void store_u16_le(uint8_t *dst, uint16_t value)
{
    dst[0] = (uint8_t)(value & 0xFFu);
    dst[1] = (uint8_t)((value >> 8u) & 0xFFu);
}

static inline void store_u32_le(uint8_t *dst, uint32_t value)
{
    dst[0] = (uint8_t)(value & 0xFFu);
    dst[1] = (uint8_t)((value >> 8u) & 0xFFu);
    dst[2] = (uint8_t)((value >> 16u) & 0xFFu);
    dst[3] = (uint8_t)((value >> 24u) & 0xFFu);
}

/* ------------------------------------------------------------------------------------------------------------------ */
/* Public functions                                                                                                   */
/* ------------------------------------------------------------------------------------------------------------------ */
void ImageProtocol_PackMetadata(const image_metadata_t *meta, uint8_t *dst)
{
    if ((meta == NULL) || (dst == NULL))
    {
        return;
    }

    dst[0] = meta->version;
    store_u32_le(&dst[1], meta->frame_counter);
    store_u16_le(&dst[5], meta->width);
    store_u16_le(&dst[7], meta->height);
    dst[9] = meta->pixel_format;
    store_u32_le(&dst[10], meta->payload_length);
}

void ImageProtocol_BuildWrapper(uint8_t *frame_buf, const image_metadata_t *meta, uint16_t crc16)
{
    if ((frame_buf == NULL) || (meta == NULL))
    {
        return;
    }

    /* Header */
    frame_buf[IMAGE_OFF_HEADER + 0u] = IMAGE_HEADER_0;
    frame_buf[IMAGE_OFF_HEADER + 1u] = IMAGE_HEADER_1;

    /* Metadata */
    ImageProtocol_PackMetadata(meta, &frame_buf[IMAGE_OFF_VERSION]);

    /* CRC (little-endian) */
    frame_buf[IMAGE_OFF_CRC + 0u] = (uint8_t)(crc16 & 0xFFu);
    frame_buf[IMAGE_OFF_CRC + 1u] = (uint8_t)((crc16 >> 8u) & 0xFFu);

    /* Tail */
    frame_buf[IMAGE_OFF_TAIL + 0u] = IMAGE_TAIL_0;
    frame_buf[IMAGE_OFF_TAIL + 1u] = IMAGE_TAIL_1;
}
