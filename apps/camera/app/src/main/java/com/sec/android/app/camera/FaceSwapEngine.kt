package com.sec.android.app.camera

import android.graphics.*
import android.util.Log
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.*
import java.util.concurrent.ExecutionException
import kotlin.math.*

class FaceSwapEngine {

    private val detector: FaceDetector

    // Stored source face
    var sourceBitmap: Bitmap? = null
        private set
    private var sourceFace: Face? = null
    private var sourceLandmarks: FaceLandmarksData? = null

    data class FaceLandmarksData(
        val bounds: Rect,
        val leftEye: PointF,
        val rightEye: PointF,
        val noseBase: PointF?,
        val mouthCenter: PointF
    )

    init {
        val options = FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_ALL)
            .setClassificationMode(FaceDetectorOptions.CLASSIFICATION_MODE_NONE)
            .setMinFaceSize(0.15f)
            .build()
        detector = FaceDetection.getClient(options)
    }

    /**
     * Set the source face to swap with.
     */
    fun setSourceFace(bitmap: Bitmap): Boolean {
        try {
            val inputImage = InputImage.fromBitmap(bitmap, 0)
            val faces = Tasks.await(detector.process(inputImage))
            if (faces.isNotEmpty()) {
                val face = faces.maxByOrNull { it.boundingBox.width() * it.boundingBox.height() }!!
                val leftEye = face.getLandmark(FaceLandmark.LEFT_EYE)?.position
                val rightEye = face.getLandmark(FaceLandmark.RIGHT_EYE)?.position
                val nose = face.getLandmark(FaceLandmark.NOSE_BASE)?.position
                val mouthL = face.getLandmark(FaceLandmark.MOUTH_LEFT)?.position
                val mouthR = face.getLandmark(FaceLandmark.MOUTH_RIGHT)?.position

                if (leftEye != null && rightEye != null) {
                    val mouthCenter = if (mouthL != null && mouthR != null) {
                        PointF((mouthL.x + mouthR.x) / 2f, (mouthL.y + mouthR.y) / 2f)
                    } else {
                        PointF((leftEye.x + rightEye.x) / 2f, (leftEye.y + rightEye.y) / 2f + face.boundingBox.height() * 0.4f)
                    }

                    sourceBitmap = bitmap
                    sourceFace = face
                    sourceLandmarks = FaceLandmarksData(
                        bounds = face.boundingBox,
                        leftEye = leftEye,
                        rightEye = rightEye,
                        noseBase = nose,
                        mouthCenter = mouthCenter
                    )
                    Log.d(TAG, "Source face successfully set with landmarks.")
                    return true
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error setting source face: ${e.message}", e)
        }
        return false
    }

    fun hasSourceFace(): Boolean = sourceBitmap != null && sourceLandmarks != null

    /**
     * Swap face on a target bitmap synchronously (used for photo capture & intent return).
     */
    fun swapFace(targetBitmap: Bitmap): Bitmap {
        if (!hasSourceFace()) return targetBitmap

        try {
            val inputImage = InputImage.fromBitmap(targetBitmap, 0)
            val faces = Tasks.await(detector.process(inputImage))

            if (faces.isEmpty()) return targetBitmap

            val resultBitmap = targetBitmap.copy(Bitmap.Config.ARGB_8888, true)
            val canvas = Canvas(resultBitmap)

            for (targetFace in faces) {
                blendFaceOntoTarget(canvas, targetFace, targetBitmap.width, targetBitmap.height)
            }
            return resultBitmap
        } catch (e: Exception) {
            Log.e(TAG, "Error during face swap: ${e.message}", e)
            return targetBitmap
        }
    }

    /**
     * Core affine transformation, color matching, and feathered blending.
     */
    private fun blendFaceOntoTarget(canvas: Canvas, targetFace: Face, targetW: Int, targetH: Int) {
        val srcBmp = sourceBitmap ?: return
        val srcLm = sourceLandmarks ?: return

        val tLeftEye = targetFace.getLandmark(FaceLandmark.LEFT_EYE)?.position ?: return
        val tRightEye = targetFace.getLandmark(FaceLandmark.RIGHT_EYE)?.position ?: return

        // 1. Calculate Eye Distance & Angle for Source and Target
        val srcEyeDx = srcLm.rightEye.x - srcLm.leftEye.x
        val srcEyeDy = srcLm.rightEye.y - srcLm.leftEye.y
        val srcEyeDist = hypot(srcEyeDx, srcEyeDy).coerceAtLeast(10f)
        val srcAngle = atan2(srcEyeDy, srcEyeDx)

        val tgtEyeDx = tRightEye.x - tLeftEye.x
        val tgtEyeDy = tRightEye.y - tLeftEye.y
        val tgtEyeDist = hypot(tgtEyeDx, tgtEyeDy).coerceAtLeast(10f)
        val tgtAngle = atan2(tgtEyeDy, tgtEyeDx)

        val scale = tgtEyeDist / srcEyeDist
        val rotationDeg = Math.toDegrees((tgtAngle - srcAngle).toDouble()).toFloat()

        // Midpoint between eyes
        val srcMidEye = PointF((srcLm.leftEye.x + srcLm.rightEye.x) / 2f, (srcLm.leftEye.y + srcLm.rightEye.y) / 2f)
        val tgtMidEye = PointF((tLeftEye.x + tRightEye.x) / 2f, (tLeftEye.y + tRightEye.y) / 2f)

        // 2. Crop Source Face with Feathered Mask
        val srcBounds = srcLm.bounds
        val padX = (srcBounds.width() * 0.15f).toInt()
        val padY = (srcBounds.height() * 0.20f).toInt()
        val cropRect = Rect(
            (srcBounds.left - padX).coerceAtLeast(0),
            (srcBounds.top - padY).coerceAtLeast(0),
            (srcBounds.right + padX).coerceAtMost(srcBmp.width),
            (srcBounds.bottom + padY).coerceAtMost(srcBmp.height)
        )

        if (cropRect.width() <= 10 || cropRect.height() <= 10) return

        val croppedFace = Bitmap.createBitmap(srcBmp, cropRect.left, cropRect.top, cropRect.width(), cropRect.height())

        // 3. Create Feathered Oval Alpha Mask
        val maskedFace = Bitmap.createBitmap(croppedFace.width, croppedFace.height, Bitmap.Config.ARGB_8888)
        val maskCanvas = Canvas(maskedFace)

        val maskPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            isDither = true
            color = Color.WHITE
        }

        // Elliptical gradient mask for smooth skin blending
        val cx = croppedFace.width / 2f
        val cy = croppedFace.height / 2f
        val radius = max(cx, cy)
        val shader = RadialGradient(
            cx, cy, radius,
            intArrayOf(Color.WHITE, Color.WHITE, Color.TRANSPARENT),
            floatArrayOf(0f, 0.65f, 1.0f),
            Shader.TileMode.CLAMP
        )
        maskPaint.shader = shader
        maskCanvas.drawOval(RectF(0f, 0f, croppedFace.width.toFloat(), croppedFace.height.toFloat()), maskPaint)

        // Combine with source face
        val paintSrcIn = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            xfermode = PorterDuffXfermode(PorterDuff.Mode.SRC_IN)
            isFilterBitmap = true
        }
        maskCanvas.drawBitmap(croppedFace, 0f, 0f, paintSrcIn)

        // 4. Matrix Transform: Translate to origin -> Scale -> Rotate -> Translate to target position
        val matrix = Matrix()
        val srcAnchorX = srcMidEye.x - cropRect.left
        val srcAnchorY = srcMidEye.y - cropRect.top

        matrix.postTranslate(-srcAnchorX, -srcAnchorY)
        matrix.postScale(scale, scale)
        matrix.postRotate(rotationDeg)
        matrix.postTranslate(tgtMidEye.x, tgtMidEye.y)

        // 5. Draw Blended Face
        val drawPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            isFilterBitmap = true
            isDither = true
            alpha = 245 // Subtle transparency for natural skin tone fusion
        }
        canvas.drawBitmap(maskedFace, matrix, drawPaint)
    }

    fun close() {
        detector.close()
    }

    companion object {
        private const val TAG = "FaceSwapEngine"
    }
}
