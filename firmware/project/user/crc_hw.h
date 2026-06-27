/*********************************************************************************************************************
 * @file    crc_hw.h
 * @brief   Hardware CRC16 driver using the PDMA CRC engine (SDL CRC example).
 *
 * CRC variant: CRC-16/CCITT-FALSE
 *   Polynomial : 0x1021
 *   Initial    : 0xFFFF
 *   RefIn      : false
 *   RefOut     : false
 *   XorOut     : 0x0000
 *
 * The PDMA CRC engine is a 32-bit LFSR. For a 16-bit polynomial the value is
 * placed in the upper 16 bits of the 32-bit registers; the result is taken from
 * the upper 16 bits of REM_RESULT.
 ********************************************************************************************************************/

#ifndef CRC_HW_H
#define CRC_HW_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize the PDMA CRC channel (DW1 channel 7).
 *
 * Reuses the exact initialization sequence from the SDL CRC example:
 *   Cy_PDMA_Disable -> Cy_PDMA_Chnl_DeInit -> Cy_PDMA_Descr_Init ->
 *   Cy_PDMA_Chnl_Init -> Cy_PDMA_Chnl_SetInterruptMask -> Cy_PDMA_Enable
 */
void CRC16_Init(void);

/**
 * @brief Calculate CRC-16/CCITT-FALSE over a contiguous data block.
 *
 * The SDL PDMA CRC descriptor supports at most 256 bytes per trigger. For
 * blocks larger than that this function splits the calculation into chunks and
 * chains the seed, producing the same result as a single CRC over the whole
 * block.
 *
 * @param data      Source data pointer.
 * @param length    Number of bytes.
 * @param seed      Initial CRC seed (use 0xFFFF for a fresh frame).
 * @param crc_out   Output pointer for the CRC result.
 * @return true     CRC calculated successfully.
 * @return false    Parameter error or DMA timeout.
 */
bool CRC16_Calculate(const uint8_t *data, uint32_t length, uint16_t seed, uint16_t *crc_out);

/**
 * @brief ISR callback for the PDMA CRC channel (DW1 channel 7).
 *
 * Called from cm7_0_isr.c. Do not call from application code.
 */
void CRC16_IRQHandler(void);

#ifdef __cplusplus
}
#endif

#endif /* CRC_HW_H */
