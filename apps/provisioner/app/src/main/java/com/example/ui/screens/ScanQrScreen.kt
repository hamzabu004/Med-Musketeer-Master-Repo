package com.example.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import android.hardware.camera2.CaptureRequest
import android.util.Size
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn
import androidx.camera.camera2.interop.Camera2CameraControl
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.CaptureRequestOptions
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.FocusMeteringAction
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.CenterFocusStrong
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.FlashOff
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material.icons.filled.Highlight
import androidx.compose.material.icons.filled.Keyboard
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.example.model.GatewayQrResult
import com.example.qr.QrCodeAnalyzer
import kotlinx.coroutines.delay
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.math.roundToInt

@Composable
fun ScanQrScreen(
    qrResult: GatewayQrResult?,
    manualInput: String,
    manualError: String?,
    onQrDetected: (String) -> Unit,
    onClearQrError: () -> Unit,
    onManualInputChange: (String) -> Unit,
    onSubmitManualInput: () -> Unit,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    var hasCameraPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        )
    }

    var showManualMode by remember { mutableStateOf(false) }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        hasCameraPermission = isGranted
        if (!isGranted) {
            showManualMode = true
        }
    }

    LaunchedEffect(Unit) {
        if (!hasCameraPermission) {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        // Tab Selector: Camera QR vs Manual Entry
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp)
                .background(
                    MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(12.dp)
                )
                .padding(4.dp)
        ) {
            Button(
                onClick = { showManualMode = false },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (!showManualMode) MaterialTheme.colorScheme.primary else Color.Transparent,
                    contentColor = if (!showManualMode) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant
                ),
                shape = RoundedCornerShape(10.dp),
                elevation = null,
                modifier = Modifier
                    .weight(1f)
                    .height(44.dp)
                    .testTag("tab_camera_qr")
            ) {
                Icon(
                    imageVector = Icons.Default.QrCodeScanner,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text("Scan OLED QR", fontWeight = FontWeight.Bold)
            }

            Button(
                onClick = { showManualMode = true },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (showManualMode) MaterialTheme.colorScheme.primary else Color.Transparent,
                    contentColor = if (showManualMode) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant
                ),
                shape = RoundedCornerShape(10.dp),
                elevation = null,
                modifier = Modifier
                    .weight(1f)
                    .height(44.dp)
                    .testTag("tab_manual_entry")
            ) {
                Icon(
                    imageVector = Icons.Default.Keyboard,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text("Manual Name", fontWeight = FontWeight.Bold)
            }
        }

        // Error Banner if scanned QR was rejected by QrParser
        if (qrResult != null && !qrResult.isValid) {
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.errorContainer
                ),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 6.dp)
                    .testTag("qr_error_banner")
            ) {
                Row(
                    modifier = Modifier.padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Default.Warning,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.error,
                        modifier = Modifier.size(24.dp)
                    )
                    Spacer(modifier = Modifier.width(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Invalid Wearable QR Code",
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                        Text(
                            text = qrResult.errorMessage ?: "Expected format: MM-WR-XXXXXX|7A2E0001...",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                    IconButton(onClick = onClearQrError) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Dismiss",
                            tint = MaterialTheme.colorScheme.onErrorContainer
                        )
                    }
                }
            }
        }

        if (showManualMode || !hasCameraPermission) {
            ManualEntryView(
                manualInput = manualInput,
                manualError = manualError,
                hasCameraPermission = hasCameraPermission,
                onRequestCameraPermission = { permissionLauncher.launch(Manifest.permission.CAMERA) },
                onManualInputChange = onManualInputChange,
                onSubmit = onSubmitManualInput
            )
        } else {
            CameraQrScannerView(
                onQrDetected = onQrDetected
            )
        }
    }
}

@OptIn(ExperimentalCamera2Interop::class)
@Composable
private fun CameraQrScannerView(
    onQrDetected: (String) -> Unit
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val density = LocalDensity.current

    var isTorchEnabled by remember { mutableStateOf(false) }
    var isAntiGlareEnabled by remember { mutableStateOf(false) }
    var isMacroModeEnabled by remember { mutableStateOf(false) }
    var currentZoom by remember { mutableFloatStateOf(1.5f) } // Default 1.5x zoom so camera doesn't need to get inside minimum focal distance
    var cameraInstance by remember { mutableStateOf<Camera?>(null) }
    var previewViewRef by remember { mutableStateOf<PreviewView?>(null) }

    // Tap-to-focus animation state
    var focusTapPosition by remember { mutableStateOf<Offset?>(null) }
    var showFocusRing by remember { mutableStateOf(false) }

    fun triggerFocusAt(x: Float, y: Float) {
        val pView = previewViewRef ?: return
        val cam = cameraInstance ?: return

        try {
            val factory = pView.meteringPointFactory
            val point = factory.createPoint(x, y)
            val action = FocusMeteringAction.Builder(
                point,
                FocusMeteringAction.FLAG_AF or FocusMeteringAction.FLAG_AE
            )
                .setAutoCancelDuration(3, TimeUnit.SECONDS)
                .build()

            cam.cameraControl.startFocusAndMetering(action)
            focusTapPosition = Offset(x, y)
            showFocusRing = true
        } catch (_: Exception) {}
    }

    fun triggerCenterFocus() {
        val pView = previewViewRef ?: return
        val centerX = pView.width / 2f
        val centerY = pView.height / 2f
        triggerFocusAt(centerX, centerY)
    }

    fun applyMacroFocusMode(enable: Boolean) {
        val cam = cameraInstance ?: return
        try {
            val camera2Control = Camera2CameraControl.from(cam.cameraControl)
            val options = CaptureRequestOptions.Builder()
                .setCaptureRequestOption(
                    CaptureRequest.CONTROL_AF_MODE,
                    if (enable) CaptureRequest.CONTROL_AF_MODE_MACRO
                    else CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE
                )
                .build()
            camera2Control.setCaptureRequestOptions(options)
            triggerCenterFocus()
        } catch (_: Exception) {}
    }

    // Auto-refocus timer: gently pulses center focus every 4s if idle
    LaunchedEffect(Unit) {
        while (true) {
            delay(4000)
            if (cameraInstance != null && previewViewRef != null) {
                triggerCenterFocus()
            }
        }
    }

    LaunchedEffect(showFocusRing) {
        if (showFocusRing) {
            delay(1200)
            showFocusRing = false
        }
    }

    val cameraExecutor = remember { Executors.newSingleThreadExecutor() }
    val analyzer = remember {
        QrCodeAnalyzer { detectedText ->
            onQrDetected(detectedText)
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            cameraExecutor.shutdown()
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
            .clip(RoundedCornerShape(20.dp))
            .background(Color.Black)
            .pointerInput(Unit) {
                detectTapGestures { offset ->
                    triggerFocusAt(offset.x, offset.y)
                }
            }
    ) {
        AndroidView(
            factory = { ctx ->
                val previewView = PreviewView(ctx).apply {
                    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                }
                previewViewRef = previewView
                val cameraProviderFuture = ProcessCameraProvider.getInstance(ctx)

                cameraProviderFuture.addListener({
                    val cameraProvider = cameraProviderFuture.get()

                    val previewBuilder = Preview.Builder().also {
                        val camera2Extender = Camera2Interop.Extender(it)
                        camera2Extender.setCaptureRequestOption(
                            CaptureRequest.CONTROL_AF_MODE,
                            CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE
                        )
                        camera2Extender.setCaptureRequestOption(
                            CaptureRequest.CONTROL_MODE,
                            CaptureRequest.CONTROL_MODE_AUTO
                        )
                    }

                    val preview = previewBuilder.build().also {
                        it.surfaceProvider = previewView.surfaceProvider
                    }

                    // High-resolution image analysis for crisp OLED rendering
                    val imageAnalysis = ImageAnalysis.Builder()
                        .setTargetResolution(Size(1280, 720))
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build()
                        .also {
                            it.setAnalyzer(cameraExecutor, analyzer)
                        }

                    val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

                    try {
                        cameraProvider.unbindAll()
                        val cam = cameraProvider.bindToLifecycle(
                            lifecycleOwner,
                            cameraSelector,
                            preview,
                            imageAnalysis
                        )
                        cameraInstance = cam
                        // Apply initial 1.5x zoom to keep optimal focal distance
                        cam.cameraControl.setZoomRatio(1.5f)
                    } catch (_: Exception) {}
                }, ContextCompat.getMainExecutor(ctx))

                previewView
            },
            modifier = Modifier
                .fillMaxSize()
                .testTag("camera_preview_view")
        )

        // Viewfinder Target Overlay
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Box(
                modifier = Modifier
                    .size(240.dp)
                    .border(
                        width = 3.dp,
                        color = MaterialTheme.colorScheme.primary,
                        shape = RoundedCornerShape(16.dp)
                    )
                    .background(Color.White.copy(alpha = 0.04f))
            )
        }

        // Tap-to-focus ring indicator
        AnimatedVisibility(
            visible = showFocusRing && focusTapPosition != null,
            enter = fadeIn(),
            exit = fadeOut()
        ) {
            focusTapPosition?.let { pos ->
                val ringSizePx = with(density) { 60.dp.toPx() }
                Box(
                    modifier = Modifier
                        .offset {
                            IntOffset(
                                (pos.x - ringSizePx / 2).roundToInt(),
                                (pos.y - ringSizePx / 2).roundToInt()
                            )
                        }
                        .size(60.dp)
                        .border(2.5.dp, MaterialTheme.colorScheme.primary, CircleShape)
                )
            }
        }

        // Top Controls Bar: Macro Focus, Anti-Glare, Focus Light
        Row(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Macro / Close-Up Focus Mode
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(20.dp))
                    .background(
                        if (isMacroModeEnabled) MaterialTheme.colorScheme.primary
                        else Color.Black.copy(alpha = 0.7f)
                    )
                    .clickable {
                        val newMacro = !isMacroModeEnabled
                        isMacroModeEnabled = newMacro
                        applyMacroFocusMode(newMacro)
                    }
                    .padding(horizontal = 10.dp, vertical = 8.dp)
                    .testTag("macro_focus_toggle")
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.Highlight,
                        contentDescription = null,
                        tint = if (isMacroModeEnabled) Color.Black else Color.White,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "Macro AF",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = if (isMacroModeEnabled) Color.Black else Color.White
                    )
                }
            }

            // Anti-Glare Exposure toggle
            IconButton(
                onClick = {
                    val newAntiGlare = !isAntiGlareEnabled
                    isAntiGlareEnabled = newAntiGlare
                    try {
                        val exposureIndex = if (newAntiGlare) -3 else 0
                        cameraInstance?.cameraControl?.setExposureCompensationIndex(exposureIndex)
                    } catch (_: Exception) {}
                },
                modifier = Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .background(
                        if (isAntiGlareEnabled) MaterialTheme.colorScheme.secondary
                        else Color.Black.copy(alpha = 0.7f)
                    )
                    .testTag("antiglare_toggle_button")
            ) {
                Icon(
                    imageVector = Icons.Default.Tune,
                    contentDescription = "OLED Anti-Glare",
                    tint = if (isAntiGlareEnabled) Color.Black else Color.White,
                    modifier = Modifier.size(20.dp)
                )
            }

            // Focus Light / Torch
            IconButton(
                onClick = {
                    val newTorch = !isTorchEnabled
                    isTorchEnabled = newTorch
                    cameraInstance?.cameraControl?.enableTorch(newTorch)
                },
                modifier = Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .background(
                        if (isTorchEnabled) MaterialTheme.colorScheme.tertiary
                        else Color.Black.copy(alpha = 0.7f)
                    )
                    .testTag("torch_toggle_button")
            ) {
                Icon(
                    imageVector = if (isTorchEnabled) Icons.Default.FlashOn else Icons.Default.FlashOff,
                    contentDescription = "Focus Light",
                    tint = if (isTorchEnabled) Color.Black else Color.White,
                    modifier = Modifier.size(20.dp)
                )
            }
        }

        // Quick Refocus Pill Button (Center Screen Assist)
        Box(
            modifier = Modifier
                .align(Alignment.Center)
                .offset(y = 150.dp)
                .clip(RoundedCornerShape(20.dp))
                .background(MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.9f))
                .clickable { triggerCenterFocus() }
                .padding(horizontal = 14.dp, vertical = 8.dp)
                .testTag("tap_to_refocus_button")
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.CenterFocusStrong,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimaryContainer,
                    modifier = Modifier.size(16.dp)
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text(
                    text = "Refocus Center",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }
        }

        // Zoom Selector (1x, 1.5x, 2x, 3x)
        Row(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 86.dp)
                .background(Color.Black.copy(alpha = 0.8f), shape = RoundedCornerShape(24.dp))
                .padding(horizontal = 8.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            listOf(1.0f, 1.5f, 2.0f, 3.0f).forEach { zoomLevel ->
                val isSelected = currentZoom == zoomLevel
                Box(
                    modifier = Modifier
                        .clip(CircleShape)
                        .background(if (isSelected) MaterialTheme.colorScheme.primary else Color.Transparent)
                        .clickable {
                            currentZoom = zoomLevel
                            cameraInstance?.cameraControl?.setZoomRatio(zoomLevel)
                            triggerCenterFocus()
                        }
                        .padding(horizontal = 10.dp, vertical = 6.dp)
                        .testTag("zoom_button_${zoomLevel}x")
                ) {
                    Text(
                        text = if (zoomLevel == 1.5f) "1.5x" else "${zoomLevel.toInt()}x",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (isSelected) Color.Black else Color.White
                    )
                }
            }
        }

        // Instructions overlay at bottom of camera view
        Surface(
            color = Color.Black.copy(alpha = 0.85f),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(12.dp)
                .fillMaxWidth()
        ) {
            Column(
                modifier = Modifier.padding(10.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "Tap screen or 'Refocus' to lock focus on OLED",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White,
                    textAlign = TextAlign.Center
                )
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = "Hold 6–8 in (15–20 cm) away with 1.5x/2x zoom. Enable Macro AF or Light if dim.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                    textAlign = TextAlign.Center
                )
            }
        }
    }
}

@Composable
private fun ManualEntryView(
    manualInput: String,
    manualError: String?,
    hasCameraPermission: Boolean,
    onRequestCameraPermission: () -> Unit,
    onManualInputChange: (String) -> Unit,
    onSubmit: () -> Unit
) {
    val scrollState = rememberScrollState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        if (!hasCameraPermission) {
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant
                ),
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(14.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.CameraAlt,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Camera Permission Not Granted",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                    }
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = "To scan the OLED QR code, camera permission is required. You can also enter the wearable name directly below.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    OutlinedButton(
                        onClick = onRequestCameraPermission,
                        modifier = Modifier.testTag("request_camera_perm_button")
                    ) {
                        Text("Grant Camera Permission")
                    }
                }
            }
            Spacer(modifier = Modifier.height(20.dp))
        }

        Box(
            modifier = Modifier
                .size(64.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.primaryContainer),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = Icons.Default.Keyboard,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(32.dp)
            )
        }

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = "Enter Wearable Name",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurface
        )

        Spacer(modifier = Modifier.height(6.dp))

        Text(
            text = "Look at your ESP32-S3 wearable OLED header. The device name begins with MM-WR- followed by 6 hex characters.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(24.dp))

        OutlinedTextField(
            value = manualInput,
            onValueChange = onManualInputChange,
            label = { Text("Wearable Name (e.g. MM-WR-A1B2C3)") },
            placeholder = { Text("MM-WR-1A2B3C") },
            singleLine = true,
            isError = manualError != null,
            supportingText = {
                if (manualError != null) {
                    Text(text = manualError, color = MaterialTheme.colorScheme.error)
                } else {
                    Text("Must match pattern: MM-WR-XXXXXX (6 hex characters)")
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .testTag("manual_gateway_name_input")
        )

        Spacer(modifier = Modifier.height(24.dp))

        Button(
            onClick = onSubmit,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp)
                .testTag("submit_gateway_name_button")
        ) {
            Icon(
                imageVector = Icons.Default.QrCodeScanner,
                contentDescription = null
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text("Find & Connect Wearable", fontWeight = FontWeight.Bold)
        }
    }
}
