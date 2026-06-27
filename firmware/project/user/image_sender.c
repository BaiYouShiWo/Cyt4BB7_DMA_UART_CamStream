/*********************************************************************************************************************
 * @file    image_sender.c
 * @brief   Image sender implementation.
 *
 * State machine:
 *   IDLE -> PREPARE_FRAME -> CALC_CRC -> START_DMA -> DMA_BUSY -> FRAME_DONE -> IDLE
 *
 * Error states recover automatically to IDLE so the next frame can be sent.
 ********************************************************************************************************************/

#include "image_sender.h"
#include "image_protocol.h"
#include "uart_dma.h"
#include "crc_hw.h"

#include <string.h>

/* ------------------------------------------------------------------------------------------------------------------ */
/* State machine                                                                                                      */
/* ------------------------------------------------------------------------------------------------------------------ */
typedef enum
{
    STATE_IDLE = 0,
    STATE_PREPARE_FRAME,
    STATE_CALC_CRC,
    STATE_START_DMA,
    STATE_DMA_BUSY,
    STATE_FRAME_DONE,
    STATE_ERROR_DMA_BUSY,
    STATE_ERROR_INVALID_PARAM,
    STATE_ERROR_CRC_TIMEOUT,
    STATE_ERROR_DMA,
} image_sender_state_t;

/* ------------------------------------------------------------------------------------------------------------------ */
/* Module data                                                                                                        */
/* ------------------------------------------------------------------------------------------------------------------ */
static uint8_t                  s_frame_buffer[IMAGE_FRAME_PADDED_SIZE];
static image_metadata_t         s_metadata;
static uint32_t                 s_frame_counter = 0u;
static image_sender_state_t     s_state = STATE_IDLE;
static uint32_t                 s_frames_sent = 0u;
static uint32_t                 s_frames_dropped = 0u;

/* ------------------------------------------------------------------------------------------------------------------ */
/* Local helpers                                                                                                      */
/* ------------------------------------------------------------------------------------------------------------------ */
static void prepare_metadata(void)
{
    s_metadata.version       = IMAGE_PROTOCOL_VERSION;
    s_metadata.frame_counter = s_frame_counter;
    s_metadata.width         = IMAGE_WIDTH;
    s_metadata.height        = IMAGE_HEIGHT;
    s_metadata.pixel_format  = IMAGE_PIXEL_FORMAT_GRAY;
    s_metadata.payload_length= IMAGE_PAYLOAD_SIZE;
}

static void state_transition(image_sender_state_t new_state)
{
    s_state = new_state;
}

/* ------------------------------------------------------------------------------------------------------------------ */
/* Public functions                                                                                                   */
/* ------------------------------------------------------------------------------------------------------------------ */
void ImageSender_Init(void)
{
    /* Initialize hardware modules in dependency order (CRC first, then UART DMA). */
    CRC16_Init();
    UART_DMA_Init();

    s_frame_counter = 0u;
    s_frames_sent   = 0u;
    s_frames_dropped= 0u;
    s_state         = STATE_IDLE;
}

bool ImageSender_IsBusy(void)
{
    return (s_state != STATE_IDLE) || UART_DMA_IsBusy();
}

bool ImageSender_SendFrame(uint8_t *image)
{
    uint16_t crc16;

    /* --- IDLE guard and parameter check --------------------------------------------------------------- */
    if (image == NULL)
    {
        state_transition(STATE_ERROR_INVALID_PARAM);
        s_frames_dropped++;
        return false;
    }

    if ((s_state != STATE_IDLE) || UART_DMA_IsBusy())
    {
        state_transition(STATE_ERROR_DMA_BUSY);
        s_frames_dropped++;
        return false;
    }

    state_transition(STATE_PREPARE_FRAME);

    /* --- Copy image into frame buffer ----------------------------------------------------------------- */
    memcpy(&s_frame_buffer[IMAGE_OFF_PAYLOAD], image, IMAGE_PAYLOAD_SIZE);

    /* --- Prepare and write metadata ------------------------------------------------------------------- */
    prepare_metadata();
    ImageProtocol_PackMetadata(&s_metadata, &s_frame_buffer[IMAGE_OFF_VERSION]);

    state_transition(STATE_CALC_CRC);

    /* --- Hardware CRC over metadata + image ----------------------------------------------------------- */
    if (!CRC16_Calculate(&s_frame_buffer[IMAGE_CRC_START_OFFSET],
                         IMAGE_CRC_LENGTH,
                         0xFFFFu,
                         &crc16))
    {
        /* CRC timeout / error. */
        state_transition(STATE_ERROR_CRC_TIMEOUT);
        s_frames_dropped++;
        return false;
    }

    /* --- Build protocol wrapper (header already ok? no, write all wrapper fields) --------------------- */
    ImageProtocol_BuildWrapper(s_frame_buffer, &s_metadata, crc16);

    state_transition(STATE_START_DMA);

    /* --- Start UART DMA ------------------------------------------------------------------------------- */
    UART_DMA_SetSourceBuffer(s_frame_buffer);

    if (!UART_DMA_SendFrame())
    {
        state_transition(STATE_ERROR_DMA);
        s_frames_dropped++;
        return false;
    }

    s_frame_counter++;
    s_frames_sent++;
    state_transition(STATE_DMA_BUSY);

    return true;
}

void ImageSender_DmaDoneCallback(void)
{
    if (s_state == STATE_DMA_BUSY)
    {
        state_transition(STATE_FRAME_DONE);
    }

    /* After any DMA completion, return to IDLE so the next frame can be sent. */
    state_transition(STATE_IDLE);
}

void ImageSender_GetStats(uint32_t *frames_sent, uint32_t *frames_dropped)
{
    if (frames_sent != NULL)
    {
        *frames_sent = s_frames_sent;
    }
    if (frames_dropped != NULL)
    {
        *frames_dropped = s_frames_dropped;
    }
}
