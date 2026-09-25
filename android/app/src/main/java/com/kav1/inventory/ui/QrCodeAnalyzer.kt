package com.kav1.inventory.ui

import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.MultiFormatReader
import com.google.zxing.NotFoundException
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.ReaderException
import com.google.zxing.common.HybridBinarizer

/**
 * Decodes QR codes from the luminance (Y) plane of CameraX YUV frames. QR codes decode in
 * any orientation, so the frame is used as-is without rotating.
 */
class QrCodeAnalyzer(private val onQrCode: (String) -> Unit) : ImageAnalysis.Analyzer {

    private val reader = MultiFormatReader().apply {
        setHints(
            mapOf(
                DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE),
                DecodeHintType.TRY_HARDER to true,
            ),
        )
    }
    private var buffer = ByteArray(0)

    override fun analyze(image: ImageProxy) {
        image.use {
            val plane = it.planes[0]
            val rowStride = plane.rowStride
            val size = rowStride * it.height
            if (buffer.size != size) buffer = ByteArray(size)
            val source = plane.buffer.apply { rewind() }
            source.get(buffer, 0, minOf(size, source.remaining()))

            val luminance = PlanarYUVLuminanceSource(
                buffer, rowStride, it.height, 0, 0, it.width, it.height, false,
            )
            try {
                val result = reader.decodeWithState(BinaryBitmap(HybridBinarizer(luminance)))
                result.text?.takeIf { text -> text.isNotBlank() }?.let { text -> onQrCode(text.trim()) }
            } catch (_: NotFoundException) {
                // No QR code in this frame.
            } catch (_: ReaderException) {
                // Found something but couldn't decode it (checksum/format); try the next frame.
            } finally {
                reader.reset()
            }
        }
    }
}
