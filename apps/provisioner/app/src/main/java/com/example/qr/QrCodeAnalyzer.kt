package com.example.qr

import androidx.annotation.OptIn
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.LuminanceSource
import com.google.zxing.MultiFormatReader
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.common.GlobalHistogramBinarizer
import com.google.zxing.common.HybridBinarizer

/**
 * High-performance dual QR code analyzer:
 * 1. Primary: Google ML Kit Barcode Scanning (neural-network backed, immune to screen flicker,
 *    reflections, and inverted OLED pixels, matching dedicated QR scanner apps).
 * 2. Fallback: Local ZXing multi-pass decoder with proper rowStride compensation and inverted
 *    luminance processing.
 */
class QrCodeAnalyzer(
    private val onQrDetected: (String) -> Unit
) : ImageAnalysis.Analyzer {

    // ML Kit Barcode Scanner configured specifically for QR codes
    private val mlKitScanner = BarcodeScanning.getClient(
        BarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
            .build()
    )

    // Fallback ZXing reader with TRY_HARDER hint
    private val zxingReader = MultiFormatReader().apply {
        val hints = mapOf(
            DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE),
            DecodeHintType.TRY_HARDER to java.lang.Boolean.TRUE,
            DecodeHintType.CHARACTER_SET to "UTF-8"
        )
        setHints(hints)
    }

    private var isThrottled = false

    @OptIn(ExperimentalGetImage::class)
    override fun analyze(image: ImageProxy) {
        if (isThrottled) {
            image.close()
            return
        }

        val mediaImage = image.image
        if (mediaImage != null) {
            val inputImage = InputImage.fromMediaImage(mediaImage, image.imageInfo.rotationDegrees)
            mlKitScanner.process(inputImage)
                .addOnSuccessListener { barcodes ->
                    var found = false
                    for (barcode in barcodes) {
                        val rawValue = barcode.rawValue
                        if (!rawValue.isNullOrBlank()) {
                            isThrottled = true
                            found = true
                            onQrDetected(rawValue)
                            break
                        }
                    }
                    if (!found) {
                        // ML Kit found nothing in this frame; attempt fallback ZXing with rowStride correction
                        tryZxingFallback(image)
                    }
                }
                .addOnFailureListener {
                    tryZxingFallback(image)
                }
                .addOnCompleteListener {
                    image.close()
                }
        } else {
            tryZxingFallback(image)
            image.close()
        }
    }

    private fun tryZxingFallback(image: ImageProxy) {
        if (isThrottled) return

        try {
            val yPlane = image.planes[0]
            val yBuffer = yPlane.buffer
            val rowStride = yPlane.rowStride
            val width = image.width
            val height = image.height
            val rotation = image.imageInfo.rotationDegrees

            // Extract contiguous Y plane correctly handling rowStride padding
            val cleanYBytes = ByteArray(width * height)
            for (row in 0 until height) {
                yBuffer.position(row * rowStride)
                yBuffer.get(cleanYBytes, row * width, width)
            }

            // Rotate Y-plane to upright orientation
            val rotatedBytes = rotateYUV(cleanYBytes, width, height, rotation)
            val effWidth = if (rotation == 90 || rotation == 270) height else width
            val effHeight = if (rotation == 90 || rotation == 270) width else height

            // 1. Try full frame
            val fullSource = PlanarYUVLuminanceSource(
                rotatedBytes,
                effWidth,
                effHeight,
                0,
                0,
                effWidth,
                effHeight,
                false
            )
            var text = tryDecodeWithZxing(fullSource)

            // 2. Try center crop (center 65% for OLED screen)
            if (text == null) {
                val cropW = (effWidth * 0.65).toInt().coerceAtLeast(1)
                val cropH = (effHeight * 0.65).toInt().coerceAtLeast(1)
                val cropL = ((effWidth - cropW) / 2).coerceAtLeast(0)
                val cropT = ((effHeight - cropH) / 2).coerceAtLeast(0)

                val croppedSource = PlanarYUVLuminanceSource(
                    rotatedBytes,
                    effWidth,
                    effHeight,
                    cropL,
                    cropT,
                    cropW,
                    cropH,
                    false
                )
                text = tryDecodeWithZxing(croppedSource)
            }

            if (!text.isNullOrBlank()) {
                isThrottled = true
                onQrDetected(text)
            }
        } catch (_: Exception) {
            // ZXing fallback error; continue scanning
        }
    }

    private fun tryDecodeWithZxing(source: LuminanceSource): String? {
        // Pass 1: HybridBinarizer (standard)
        try {
            val result = zxingReader.decodeWithState(BinaryBitmap(HybridBinarizer(source)))
            if (!result.text.isNullOrBlank()) return result.text
        } catch (_: Exception) {} finally {
            zxingReader.reset()
        }

        // Pass 2: Inverted HybridBinarizer (OLED white-on-black)
        try {
            val result = zxingReader.decodeWithState(BinaryBitmap(HybridBinarizer(source.invert())))
            if (!result.text.isNullOrBlank()) return result.text
        } catch (_: Exception) {} finally {
            zxingReader.reset()
        }

        // Pass 3: GlobalHistogramBinarizer (flicker / PWM stripe tolerant)
        try {
            val result = zxingReader.decodeWithState(BinaryBitmap(GlobalHistogramBinarizer(source)))
            if (!result.text.isNullOrBlank()) return result.text
        } catch (_: Exception) {} finally {
            zxingReader.reset()
        }

        // Pass 4: Inverted GlobalHistogramBinarizer
        try {
            val result = zxingReader.decodeWithState(BinaryBitmap(GlobalHistogramBinarizer(source.invert())))
            if (!result.text.isNullOrBlank()) return result.text
        } catch (_: Exception) {} finally {
            zxingReader.reset()
        }

        return null
    }

    private fun rotateYUV(data: ByteArray, width: Int, height: Int, rotationDegrees: Int): ByteArray {
        if (rotationDegrees == 0) return data
        val rotated = ByteArray(data.size)
        when (rotationDegrees) {
            90 -> {
                var i = 0
                for (x in 0 until width) {
                    for (y in height - 1 downTo 0) {
                        rotated[i++] = data[y * width + x]
                    }
                }
            }
            180 -> {
                var i = 0
                for (idx in data.indices.reversed()) {
                    rotated[i++] = data[idx]
                }
            }
            270 -> {
                var i = 0
                for (x in width - 1 downTo 0) {
                    for (y in 0 until height) {
                        rotated[i++] = data[y * width + x]
                    }
                }
            }
            else -> return data
        }
        return rotated
    }

    fun resetThrottle() {
        isThrottled = false
    }
}
