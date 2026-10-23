package com.example

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.model.SetupScreen
import com.example.ui.MainViewModel
import com.example.ui.components.HeaderBanner
import com.example.ui.components.TestChecklistDialog
import com.example.ui.screens.DeviceDiscoveryScreen
import com.example.ui.screens.PairingScreen
import com.example.ui.screens.ResultScreen
import com.example.ui.screens.ReviewSendScreen
import com.example.ui.screens.ScanQrScreen
import com.example.ui.screens.SettingsFormScreen
import com.example.ui.screens.WelcomeScreen
import com.example.ui.theme.MedMusketeerTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MedMusketeerTheme {
                MainApp()
            }
        }
    }
}

@Composable
fun MainApp(viewModel: MainViewModel = viewModel()) {
    val currentScreen by viewModel.currentScreen.collectAsStateWithLifecycle()
    val qrResult by viewModel.qrResult.collectAsStateWithLifecycle()
    val targetGatewayName by viewModel.targetGatewayName.collectAsStateWithLifecycle()
    val config by viewModel.config.collectAsStateWithLifecycle()
    val validation by viewModel.validationResult.collectAsStateWithLifecycle()
    val manualInput by viewModel.manualDeviceInput.collectAsStateWithLifecycle()
    val manualError by viewModel.manualDeviceError.collectAsStateWithLifecycle()
    val transferSuccess by viewModel.transferSuccess.collectAsStateWithLifecycle()
    val transferErrorReason by viewModel.transferErrorReason.collectAsStateWithLifecycle()
    val showChecklist by viewModel.showChecklistDialog.collectAsStateWithLifecycle()

    val connectionStage by viewModel.bleManager.connectionStage.collectAsStateWithLifecycle()
    val connectedDevice by viewModel.bleManager.connectedDevice.collectAsStateWithLifecycle()
    val scannedDevices by viewModel.bleManager.scannedDevices.collectAsStateWithLifecycle()
    val statusMessage by viewModel.bleManager.statusMessage.collectAsStateWithLifecycle()
    val currentMtu by viewModel.bleManager.currentMtu.collectAsStateWithLifecycle()

    BackHandler(enabled = currentScreen != SetupScreen.WELCOME) {
        viewModel.handleBackNavigation()
    }

    Scaffold(
        topBar = {
            HeaderBanner(
                title = when (currentScreen) {
                    SetupScreen.WELCOME -> "MedMusketeer Gateway"
                    SetupScreen.SCAN_QR -> "Scan OLED QR"
                    SetupScreen.DISCOVERY -> "BLE Discovery"
                    SetupScreen.PAIRING -> "Secure Pairing"
                    SetupScreen.CONFIG_FORM -> "Network & MQTT"
                    SetupScreen.REVIEW_SEND -> "Review Settings"
                    SetupScreen.RESULT -> "Provisioning Status"
                },
                subtitle = targetGatewayName,
                showBackButton = currentScreen != SetupScreen.WELCOME,
                onBackClick = { viewModel.handleBackNavigation() },
                onChecklistClick = { viewModel.toggleChecklist(true) }
            )
        },
        contentWindowInsets = WindowInsets.safeDrawing,
        modifier = Modifier.fillMaxSize()
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
        ) {
            when (currentScreen) {
                SetupScreen.WELCOME -> {
                    WelcomeScreen(
                        onStartSetup = { viewModel.navigateTo(SetupScreen.SCAN_QR) },
                        onManualEntry = { viewModel.navigateTo(SetupScreen.SCAN_QR) },
                        onOpenChecklist = { viewModel.toggleChecklist(true) }
                    )
                }

                SetupScreen.SCAN_QR -> {
                    ScanQrScreen(
                        qrResult = qrResult,
                        manualInput = manualInput,
                        manualError = manualError,
                        onQrDetected = { viewModel.onQrScanned(it) },
                        onClearQrError = { viewModel.clearQrError() },
                        onManualInputChange = { viewModel.updateManualDeviceInput(it) },
                        onSubmitManualInput = { viewModel.submitManualDeviceName() },
                        onBack = { viewModel.handleBackNavigation() }
                    )
                }

                SetupScreen.DISCOVERY -> {
                    DeviceDiscoveryScreen(
                        targetGatewayName = targetGatewayName,
                        connectionStage = connectionStage,
                        statusMessage = statusMessage,
                        currentMtu = currentMtu,
                        devices = scannedDevices,
                        onSelectDevice = { viewModel.connectToDevice(it) },
                        onRetryScan = { viewModel.startDiscoveryForGateway() },
                        onCancelScan = { viewModel.handleBackNavigation() }
                    )
                }

                SetupScreen.PAIRING -> {
                    PairingScreen(
                        device = connectedDevice,
                        connectionStage = connectionStage,
                        statusMessage = statusMessage,
                        onTriggerBonding = { viewModel.initiateBonding() },
                        onProceed = { viewModel.navigateTo(SetupScreen.CONFIG_FORM) },
                        onCancel = { viewModel.handleBackNavigation() }
                    )
                }

                SetupScreen.CONFIG_FORM -> {
                    SettingsFormScreen(
                        config = config,
                        validation = validation,
                        onConfigChange = { ssid, password, isOpen, brokerHost, brokerPort ->
                            viewModel.updateConfig(ssid, password, isOpen, brokerHost, brokerPort)
                        },
                        onProceedToReview = { viewModel.proceedToReview() }
                    )
                }

                SetupScreen.REVIEW_SEND -> {
                    ReviewSendScreen(
                        targetDeviceName = targetGatewayName,
                        config = config,
                        connectionStage = connectionStage,
                        statusMessage = statusMessage,
                        onSend = { viewModel.sendSettings() },
                        onEdit = { viewModel.navigateTo(SetupScreen.CONFIG_FORM) }
                    )
                }

                SetupScreen.RESULT -> {
                    ResultScreen(
                        targetDeviceName = targetGatewayName,
                        isSuccess = transferSuccess,
                        errorReason = transferErrorReason,
                        onRetry = { viewModel.navigateTo(SetupScreen.REVIEW_SEND) },
                        onConfigureAnother = { viewModel.resetAndConfigureAnother() }
                    )
                }
            }
        }
    }

    if (showChecklist) {
        TestChecklistDialog(
            onDismiss = { viewModel.toggleChecklist(false) }
        )
    }
}
