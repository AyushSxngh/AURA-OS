package com.sec.android.app.camera

import android.Manifest
import android.annotation.SuppressLint
import android.content.ContentValues
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.util.Log
import android.view.View
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.io.*
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private lateinit var viewFinder: PreviewView
    private lateinit var streamView: ImageView
    private lateinit var faceOverlayView: ImageView
    private lateinit var offlineOverlay: View
    private lateinit var tvStatusBadge: TextView
    private lateinit var btnEnhancer: Button
    private lateinit var btnMirror: Button
    private lateinit var btnZoom: Button
    private lateinit var btnPickFace: Button
    private lateinit var btnToggleMode: Button
    private lateinit var btnRetry: Button
    private lateinit var btnFallbackCamera: Button
    private lateinit var btnCapture: Button
    private lateinit var btnOpenGallery: Button
    private lateinit var imgSourcePreview: ImageView
    private lateinit var tvSourceName: TextView

    private val mainHandler = Handler(Looper.getMainLooper())
    private val backgroundExecutor: ExecutorService = Executors.newFixedThreadPool(3)
    private val cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    private val faceSwapEngine = FaceSwapEngine()

    @Volatile
    private var isStreaming = false
    @Volatile
    private var latestBitmap: Bitmap? = null
    @Volatile
    private var isEnhancerOn = false
    @Volatile
    private var isMirrorOn = true
    @Volatile
    private var isNormalZoom = true // True = 1.0x Normal Full-Frame (FIT_CENTER); False = Fill-Screen Crop (CENTER_CROP)
    @Volatile
    private var isHostStreamMode = false // False = On-device standalone; True = Mac CoreML stream

    private var imageCapture: ImageCapture? = null
    private var cameraProvider: ProcessCameraProvider? = null

    private var hostBaseUrl = "http://127.0.0.1:8080"
    private val candidateHosts = listOf(
        "http://127.0.0.1:8080",
        "http://10.0.2.2:8080",
        "http://10.11.13.1:8080"
    )

    // Gallery Picker for Face Swapping
    private val pickFaceLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        if (uri != null) {
            handleSourceFaceSelected(uri)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        initViews()
        setupListeners()

        if (allPermissionsGranted()) {
            startApp()
        } else {
            ActivityCompat.requestPermissions(
                this, REQUIRED_PERMISSIONS, REQUEST_CODE_PERMISSIONS
            )
        }
    }

    private fun initViews() {
        viewFinder = findViewById(R.id.viewFinder)
        streamView = findViewById(R.id.streamView)
        faceOverlayView = findViewById(R.id.faceOverlayView)
        offlineOverlay = findViewById(R.id.offlineOverlay)
        tvStatusBadge = findViewById(R.id.tv_status_badge)
        btnEnhancer = findViewById(R.id.btn_enhancer)
        btnMirror = findViewById(R.id.btn_mirror)
        btnZoom = findViewById(R.id.btn_zoom)
        btnPickFace = findViewById(R.id.btn_pick_face)
        btnToggleMode = findViewById(R.id.btn_toggle_mode)
        btnRetry = findViewById(R.id.btn_retry_connection)
        btnFallbackCamera = findViewById(R.id.btn_fallback_camera)
        btnCapture = findViewById(R.id.image_capture_button)
        btnOpenGallery = findViewById(R.id.btn_open_gallery)
        imgSourcePreview = findViewById(R.id.img_source_preview)
        tvSourceName = findViewById(R.id.tv_source_name)
    }

    private fun setupListeners() {
        btnCapture.setOnClickListener { takePhoto() }

        btnPickFace.setOnClickListener {
            pickFaceLauncher.launch("image/*")
        }

        btnEnhancer.setOnClickListener {
            isEnhancerOn = !isEnhancerOn
            btnEnhancer.text = if (isEnhancerOn) "✨ Enhanced" else "✨ Enhance"
            sendSetting("enable_enhancer", isEnhancerOn)
        }

        btnMirror.setOnClickListener {
            isMirrorOn = !isMirrorOn
            btnMirror.text = if (isMirrorOn) "🪞 Mirrored" else "🪞 Normal"
            sendSetting("live_mirror", isMirrorOn)
        }

        btnZoom.setOnClickListener {
            toggleZoomMode()
        }

        btnToggleMode.setOnClickListener {
            if (isHostStreamMode) {
                switchToOnDeviceMode()
            } else {
                startApp()
            }
        }

        btnRetry.setOnClickListener {
            offlineOverlay.visibility = View.GONE
            startApp()
        }

        btnFallbackCamera.setOnClickListener {
            switchToOnDeviceMode()
        }

        btnOpenGallery.setOnClickListener {
            val intent = Intent(Intent.ACTION_VIEW).apply {
                type = "image/*"
            }
            try {
                startActivity(intent)
            } catch (e: Exception) {
                Toast.makeText(this, "Gallery not available", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun toggleZoomMode() {
        isNormalZoom = !isNormalZoom
        applyZoomMode()
    }

    private fun applyZoomMode() {
        if (isNormalZoom) {
            btnZoom.text = "🔍 1.0x"
            streamView.scaleType = ImageView.ScaleType.FIT_CENTER
            faceOverlayView.scaleType = ImageView.ScaleType.FIT_CENTER
            viewFinder.scaleType = PreviewView.ScaleType.FIT_CENTER
            Toast.makeText(this, "Zoom: 1.0x Normal (Full View)", Toast.LENGTH_SHORT).show()
        } else {
            btnZoom.text = "🔍 Fill"
            streamView.scaleType = ImageView.ScaleType.CENTER_CROP
            faceOverlayView.scaleType = ImageView.ScaleType.CENTER_CROP
            viewFinder.scaleType = PreviewView.ScaleType.FILL_CENTER
            Toast.makeText(this, "Zoom: Fill Screen (Cropped)", Toast.LENGTH_SHORT).show()
        }
    }

    private fun startApp() {
        offlineOverlay.visibility = View.VISIBLE
        backgroundExecutor.execute {
            var hostOnline = false
            for (candidate in candidateHosts) {
                try {
                    val url = URL("$candidate/api/status")
                    val conn = url.openConnection() as HttpURLConnection
                    conn.connectTimeout = 800
                    conn.readTimeout = 800
                    if (conn.responseCode == 200) {
                        hostBaseUrl = candidate
                        hostOnline = true
                        conn.disconnect()
                        break
                    }
                    conn.disconnect()
                } catch (ignored: Exception) {}
            }

            mainHandler.post {
                offlineOverlay.visibility = View.GONE
                if (hostOnline) {
                    switchToHostStreamMode()
                } else {
                    switchToOnDeviceMode()
                }
            }
        }
    }

    // =========================================================================
    // MODE 1: ON-DEVICE STANDALONE DEEPFAKE CAMERA (100% Individual inside APK)
    // =========================================================================
    private fun switchToOnDeviceMode() {
        isStreaming = false
        isHostStreamMode = false

        streamView.visibility = View.GONE
        offlineOverlay.visibility = View.GONE
        viewFinder.visibility = View.VISIBLE
        faceOverlayView.visibility = View.VISIBLE

        btnToggleMode.text = "🟣"
        tvStatusBadge.text = "🟣 On-Device AI (Standalone)"
        tvStatusBadge.setTextColor(0xFF9B59B6.toInt())
        tvStatusBadge.setBackgroundColor(0x339B59B6.toInt())

        startCameraX()
    }

    private fun loadDefaultFaceIfAvailable() {
        if (!faceSwapEngine.hasSourceFace()) {
            backgroundExecutor.execute {
                try {
                    val stream = assets.open("default_face.jpg")
                    val bmp = BitmapFactory.decodeStream(stream)
                    stream.close()
                    if (bmp != null) {
                        val ok = faceSwapEngine.setSourceFace(bmp)
                        if (ok) {
                            mainHandler.post {
                                imgSourcePreview.setImageBitmap(bmp)
                                tvSourceName.text = "Face: Default Avatar"
                            }
                        }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Default face asset not found: ${e.message}")
                }
            }
        }
    }

    @SuppressLint("UnsafeOptInUsageError")
    private fun startCameraX() {
        loadDefaultFaceIfAvailable()
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            cameraProvider = cameraProviderFuture.get()

            viewFinder.scaleType = if (isNormalZoom) PreviewView.ScaleType.FIT_CENTER else PreviewView.ScaleType.FILL_CENTER
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(viewFinder.surfaceProvider)
            }

            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .build()

            val imageAnalysis = ImageAnalysis.Builder()
                .setTargetResolution(android.util.Size(480, 640))
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()

            var isAnalyzing = false
            imageAnalysis.setAnalyzer(cameraExecutor) { imageProxy ->
                if (isAnalyzing || !faceSwapEngine.hasSourceFace()) {
                    imageProxy.close()
                    return@setAnalyzer
                }
                isAnalyzing = true
                try {
                    val bitmap = imageProxyToBitmap(imageProxy)
                    if (bitmap != null) {
                        val swapped = faceSwapEngine.swapFace(bitmap)
                        mainHandler.post {
                            faceOverlayView.setImageBitmap(swapped)
                            faceOverlayView.visibility = View.VISIBLE
                        }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Analysis error: ${e.message}")
                } finally {
                    isAnalyzing = false
                    imageProxy.close()
                }
            }

            val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

            try {
                cameraProvider?.unbindAll()
                val camera = cameraProvider?.bindToLifecycle(this, cameraSelector, preview, imageCapture, imageAnalysis)
                camera?.cameraControl?.setZoomRatio(1.0f)
            } catch (exc: Exception) {
                Log.e(TAG, "CameraX binding failed: ${exc.message}")
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun stopCameraX() {
        try {
            cameraProvider?.unbindAll()
        } catch (ignored: Exception) {}
    }

    // =========================================================================
    // MODE 2: MAC COREML STREAM (Ultra-Smooth 60 FPS)
    // =========================================================================
    private fun switchToHostStreamMode() {
        stopCameraX()
        isHostStreamMode = true
        isStreaming = true

        viewFinder.visibility = View.GONE
        faceOverlayView.visibility = View.GONE
        streamView.visibility = View.VISIBLE

        btnToggleMode.text = "🟢"
        tvStatusBadge.text = "🟢 Host Connected"
        tvStatusBadge.setTextColor(0xFF2ECC71.toInt())
        tvStatusBadge.setBackgroundColor(0x332ECC71.toInt())

        startMjpegStream()
    }

    private fun startMjpegStream() {
        backgroundExecutor.execute {
            var connection: HttpURLConnection? = null
            var inputStream: InputStream? = null

            try {
                val url = URL("$hostBaseUrl/stream")
                connection = url.openConnection() as HttpURLConnection
                connection.connectTimeout = 3000
                connection.readTimeout = 5000
                connection.doInput = true
                connection.connect()

                if (connection.responseCode == 200) {
                    mainHandler.post {
                        offlineOverlay.visibility = View.GONE
                        tvStatusBadge.text = "🟢 Host Connected"
                        tvStatusBadge.setTextColor(0xFF2ECC71.toInt())
                        tvStatusBadge.setBackgroundColor(0x332ECC71.toInt())
                    }

                    inputStream = BufferedInputStream(connection.inputStream)
                    readMjpegStream(inputStream)
                } else {
                    handleHostFailure()
                }
            } catch (e: Exception) {
                Log.w(TAG, "Stream error: ${e.message}")
                handleHostFailure()
            } finally {
                try { inputStream?.close() } catch (ignored: Exception) {}
                try { connection?.disconnect() } catch (ignored: Exception) {}
                isStreaming = false
            }
        }
    }

    private fun readMjpegStream(inputStream: InputStream) {
        val frameDataStream = ByteArrayOutputStream()

        while (isStreaming && !isFinishing) {
            var prevByte = -1
            var currByte = inputStream.read()

            while (currByte != -1) {
                if (prevByte == 0xFF && currByte == 0xD8) {
                    frameDataStream.reset()
                    frameDataStream.write(0xFF)
                    frameDataStream.write(0xD8)
                    break
                }
                prevByte = currByte
                currByte = inputStream.read()
            }

            if (currByte == -1) break

            prevByte = -1
            currByte = inputStream.read()
            while (currByte != -1) {
                frameDataStream.write(currByte)
                if (prevByte == 0xFF && currByte == 0xD9) {
                    val jpegBytes = frameDataStream.toByteArray()
                    val bitmap = BitmapFactory.decodeByteArray(jpegBytes, 0, jpegBytes.size)
                    if (bitmap != null) {
                        latestBitmap = bitmap
                        mainHandler.post {
                            streamView.setImageBitmap(bitmap)
                        }
                    }
                    break
                }
                prevByte = currByte
                currByte = inputStream.read()
            }
        }
    }

    private fun handleHostFailure() {
        isStreaming = false
        mainHandler.post {
            // Auto-fallback to On-Device Standalone mode
            Toast.makeText(this, "Mac stream offline. Running in On-Device Standalone mode.", Toast.LENGTH_SHORT).show()
            switchToOnDeviceMode()
        }
    }

    // =========================================================================
    // FACE SELECTION (Updates On-Device Engine + Host Streamer)
    // =========================================================================
    private fun handleSourceFaceSelected(uri: Uri) {
        tvSourceName.text = "Loading face..."
        backgroundExecutor.execute {
            try {
                val inputStream = contentResolver.openInputStream(uri) ?: return@execute
                val bytes = inputStream.readBytes()
                inputStream.close()

                val sourceBmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                if (sourceBmp != null) {
                    val success = faceSwapEngine.setSourceFace(sourceBmp)

                    // Also try uploading to host stream server if available
                    try {
                        val url = URL("$hostBaseUrl/api/set_source")
                        val conn = url.openConnection() as HttpURLConnection
                        conn.requestMethod = "POST"
                        conn.setRequestProperty("Content-Type", "image/jpeg")
                        conn.connectTimeout = 2000
                        conn.readTimeout = 3000
                        conn.doOutput = true
                        val os = conn.outputStream
                        os.write(bytes)
                        os.flush()
                        os.close()
                        conn.responseCode
                        conn.disconnect()
                    } catch (ignored: Exception) {}

                    mainHandler.post {
                        if (success) {
                            imgSourcePreview.setImageBitmap(sourceBmp)
                            tvSourceName.text = "Face: Custom Photo"
                            Toast.makeText(this, "✅ Face loaded for DeepFake!", Toast.LENGTH_SHORT).show()
                        } else {
                            tvSourceName.text = "Face: Default"
                            Toast.makeText(this, "⚠️ No face detected in image. Please choose another.", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            } catch (e: Exception) {
                mainHandler.post {
                    tvSourceName.text = "Face: Default"
                    Toast.makeText(this, "Failed to load face: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    // =========================================================================
    // PHOTO CAPTURE & DEFAULT CAMERA INTENT (ACTION_IMAGE_CAPTURE)
    // =========================================================================
    private fun takePhoto() {
        if (isHostStreamMode && latestBitmap != null) {
            saveAndReturnBitmap(latestBitmap!!)
        } else if (imageCapture != null) {
            takeOnDevicePhoto()
        } else {
            Toast.makeText(this, "Camera not ready", Toast.LENGTH_SHORT).show()
        }
    }

    private fun takeOnDevicePhoto() {
        val capture = imageCapture ?: return

        capture.takePicture(
            cameraExecutor,
            object : ImageCapture.OnImageCapturedCallback() {
                override fun onCaptureSuccess(image: ImageProxy) {
                    val bitmap = imageProxyToBitmap(image)
                    image.close()

                    if (bitmap != null) {
                        // Apply On-Device DeepFake Face Swap!
                        val swappedBitmap = if (faceSwapEngine.hasSourceFace()) {
                            faceSwapEngine.swapFace(bitmap)
                        } else {
                            bitmap
                        }
                        saveAndReturnBitmap(swappedBitmap)
                    } else {
                        mainHandler.post {
                            Toast.makeText(baseContext, "Failed to process photo", Toast.LENGTH_SHORT).show()
                        }
                    }
                }

                override fun onError(exception: ImageCaptureException) {
                    mainHandler.post {
                        Toast.makeText(baseContext, "Capture error: ${exception.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        )
    }

    private fun imageProxyToBitmap(image: ImageProxy): Bitmap? {
        val planeProxy = image.planes[0]
        val buffer = planeProxy.buffer
        val bytes = ByteArray(buffer.remaining())
        buffer.get(bytes)
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return null

        // Handle rotation if needed
        val rotationDegrees = image.imageInfo.rotationDegrees
        return if (rotationDegrees != 0) {
            val matrix = android.graphics.Matrix().apply { postRotate(rotationDegrees.toFloat()) }
            Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        } else {
            bitmap
        }
    }

    private fun saveAndReturnBitmap(bitmap: Bitmap) {
        val name = "IMG_" + SimpleDateFormat(FILENAME_FORMAT, Locale.US).format(System.currentTimeMillis())
        val isIntentCapture = intent?.action == MediaStore.ACTION_IMAGE_CAPTURE ||
                intent?.action == MediaStore.ACTION_IMAGE_CAPTURE_SECURE

        val outputUri = intent?.getParcelableExtra<Uri>(MediaStore.EXTRA_OUTPUT)

        backgroundExecutor.execute {
            try {
                var targetUri = outputUri

                if (targetUri == null) {
                    val contentValues = ContentValues().apply {
                        put(MediaStore.MediaColumns.DISPLAY_NAME, "$name.jpg")
                        put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg")
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                            put(MediaStore.Images.Media.RELATIVE_PATH, "DCIM/Camera")
                        }
                    }
                    targetUri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, contentValues)
                }

                if (targetUri != null) {
                    val outStream = contentResolver.openOutputStream(targetUri)
                    if (outStream != null) {
                        bitmap.compress(Bitmap.CompressFormat.JPEG, 95, outStream)
                        outStream.flush()
                        outStream.close()

                        mainHandler.post {
                            if (isIntentCapture) {
                                val resultIntent = Intent().apply {
                                    data = targetUri
                                    putExtra(MediaStore.EXTRA_OUTPUT, targetUri)
                                    if (outputUri == null) {
                                        // Some apps expect the thumbnail bitmap in the "data" extra
                                        val maxDim = 320
                                        val w = bitmap.width
                                        val h = bitmap.height
                                        val scale = maxDim.toFloat() / maxOf(w, h)
                                        val thumb = Bitmap.createScaledBitmap(bitmap, (w * scale).toInt(), (h * scale).toInt(), true)
                                        putExtra("data", thumb)
                                    }
                                }
                                setResult(RESULT_OK, resultIntent)
                                finish()
                            } else {
                                Toast.makeText(this, "Photo saved", Toast.LENGTH_SHORT).show()
                            }
                        }
                        return@execute
                    }
                }
                mainHandler.post {
                    Toast.makeText(this, "Failed to save photo", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                mainHandler.post {
                    Toast.makeText(this, "Save error: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun sendSetting(key: String, value: Boolean) {
        backgroundExecutor.execute {
            try {
                val url = URL("$hostBaseUrl/api/settings")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.doOutput = true
                val json = JSONObject().apply { put(key, value) }
                val os = conn.outputStream
                os.write(json.toString().toByteArray())
                os.flush()
                os.close()
                conn.responseCode
                conn.disconnect()
            } catch (ignored: Exception) {}
        }
    }

    // =========================================================================
    // LIFECYCLE & PERMISSIONS
    // =========================================================================
    private fun allPermissionsGranted() = REQUIRED_PERMISSIONS.all {
        ContextCompat.checkSelfPermission(baseContext, it) == PackageManager.PERMISSION_GRANTED
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_CODE_PERMISSIONS && allPermissionsGranted()) {
            startApp()
        } else {
            Toast.makeText(this, "Permissions required for camera operation", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        isStreaming = false
        stopCameraX()
        faceSwapEngine.close()
        backgroundExecutor.shutdown()
        cameraExecutor.shutdown()
    }

    companion object {
        private const val TAG = "Camera"
        private const val FILENAME_FORMAT = "yyyyMMdd_HHmmss"
        private const val REQUEST_CODE_PERMISSIONS = 10
        private val REQUIRED_PERMISSIONS = mutableListOf(
            Manifest.permission.CAMERA,
            Manifest.permission.RECORD_AUDIO
        ).apply {
            if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.P) {
                add(Manifest.permission.WRITE_EXTERNAL_STORAGE)
            }
        }.toTypedArray()
    }
}
