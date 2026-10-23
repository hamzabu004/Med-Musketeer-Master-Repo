package com.example.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.ble.BleEvent
import com.example.ble.BleManager
import com.example.model.ConnectionStage
import com.example.model.GatewayDevice
import com.example.model.GatewayQrResult
import com.example.model.ProvisioningConfig
import com.example.model.SetupScreen
import com.example.model.ValidationResult
import com.example.qr.QrParser
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application) {

    val bleManager = BleManager(application.applicationContext)

    // Current navigation screen
    private val _currentScreen = MutableStateFlow(SetupScreen.WELCOME)
    val currentScreen: StateFlow<SetupScreen> = _currentScreen.asStateFlow()

    // Scanned QR result
    private val _qrResult = MutableStateFlow<GatewayQrResult?>(null)
    val qrResult: StateFlow<GatewayQrResult?> = _qrResult.asStateFlow()

    // Target gateway name (e.g. MM-GW-A1B2C3)
    private val _targetGatewayName = MutableStateFlow<String?>(null)
    val targetGatewayName: StateFlow<String?> = _targetGatewayName.asStateFlow()

    // Provisioning settings form
    private val _config = MutableStateFlow(ProvisioningConfig(brokerHost = "192.168.1.20", brokerPort = 1883))
    val config: StateFlow<ProvisioningConfig> = _config.asStateFlow()

    // Field-level validation errors
    private val _validationResult = MutableStateFlow(ValidationResult(isValid = false))
    val validationResult: StateFlow<ValidationResult> = _validationResult.asStateFlow()

    // Manual device input state
    private val _manualDeviceInput = MutableStateFlow("")
    val manualDeviceInput: StateFlow<String> = _manualDeviceInput.asStateFlow()

    private val _manualDeviceError = MutableStateFlow<String?>(null)
    val manualDeviceError: StateFlow<String?> = _manualDeviceError.asStateFlow()

    // Transfer result status details
    private val _transferSuccess = MutableStateFlow(false)
    val transferSuccess: StateFlow<Boolean> = _transferSuccess.asStateFlow()

    private val _transferErrorReason = MutableStateFlow<String?>(null)
    val transferErrorReason: StateFlow<String?> = _transferErrorReason.asStateFlow()

    // Test checklist modal visibility
    private val _showChecklistDialog = MutableStateFlow(false)
    val showChecklistDialog: StateFlow<Boolean> = _showChecklistDialog.asStateFlow()

    init {
        // Observe BLE events
        viewModelScope.launch {
            bleManager.eventFlow.collectLatest { event ->
                when (event) {
                    is BleEvent.BondingSuccess -> {
                        _currentScreen.value = SetupScreen.CONFIG_FORM
                    }
                    is BleEvent.BondingFailed -> {
                        _transferErrorReason.value = event.reason
                    }
                    is BleEvent.WriteSuccess -> {
                        _transferSuccess.value = true
                        _currentScreen.value = SetupScreen.RESULT
                    }
                    is BleEvent.WriteFailed -> {
                        _transferSuccess.value = false
                        _transferErrorReason.value = event.reason
                        _currentScreen.value = SetupScreen.RESULT
                    }
                    is BleEvent.Error -> {
                        _transferErrorReason.value = event.message
                    }
                    is BleEvent.ScanTimeout -> {
                        // Handled in UI
                    }
                }
            }
        }

        // Observe connection stages to advance screens when appropriate
        viewModelScope.launch {
            bleManager.connectionStage.collectLatest { stage ->
                when (stage) {
                    ConnectionStage.BONDED -> {
                        if (_currentScreen.value == SetupScreen.PAIRING || _currentScreen.value == SetupScreen.DISCOVERY) {
                            _currentScreen.value = SetupScreen.CONFIG_FORM
                        }
                    }
                    ConnectionStage.WAITING_FOR_BONDING -> {
                        if (_currentScreen.value == SetupScreen.DISCOVERY) {
                            _currentScreen.value = SetupScreen.PAIRING
                        }
                    }
                    else -> {}
                }
            }
        }
    }

    fun navigateTo(screen: SetupScreen) {
        _currentScreen.value = screen
    }

    fun handleBackNavigation(): Boolean {
        return when (_currentScreen.value) {
            SetupScreen.WELCOME -> false
            SetupScreen.SCAN_QR -> {
                _currentScreen.value = SetupScreen.WELCOME
                true
            }
            SetupScreen.DISCOVERY -> {
                bleManager.stopScan()
                _currentScreen.value = SetupScreen.SCAN_QR
                true
            }
            SetupScreen.PAIRING -> {
                bleManager.disconnectAndClose()
                _currentScreen.value = SetupScreen.DISCOVERY
                true
            }
            SetupScreen.CONFIG_FORM -> {
                _currentScreen.value = SetupScreen.PAIRING
                true
            }
            SetupScreen.REVIEW_SEND -> {
                _currentScreen.value = SetupScreen.CONFIG_FORM
                true
            }
            SetupScreen.RESULT -> {
                resetAndConfigureAnother()
                true
            }
        }
    }

    fun onQrScanned(rawText: String) {
        val result = QrParser.parse(rawText)
        _qrResult.value = result
        if (result.isValid) {
            _targetGatewayName.value = result.deviceName
            startDiscoveryForGateway(result.deviceName)
        }
    }

    fun clearQrError() {
        _qrResult.value = null
    }

    fun updateManualDeviceInput(text: String) {
        _manualDeviceInput.value = text
        _manualDeviceError.value = null
    }

    fun submitManualDeviceName(): Boolean {
        val result = QrParser.validateDeviceName(_manualDeviceInput.value)
        return if (result.isSuccess) {
            val name = result.getOrThrow()
            _manualDeviceError.value = null
            _targetGatewayName.value = name
            startDiscoveryForGateway(name)
            true
        } else {
            _manualDeviceError.value = result.exceptionOrNull()?.message ?: "Invalid device name"
            false
        }
    }

    fun startDiscoveryForGateway(targetName: String? = _targetGatewayName.value) {
        _targetGatewayName.value = targetName
        _currentScreen.value = SetupScreen.DISCOVERY
        bleManager.startActiveScan(targetName)
    }

    fun connectToDevice(device: GatewayDevice) {
        _targetGatewayName.value = device.name
        bleManager.connectToDevice(device)
    }

    fun initiateBonding() {
        bleManager.initiateBonding()
    }

    fun updateConfig(
        ssid: String? = null,
        password: String? = null,
        isOpenWifi: Boolean? = null,
        brokerHost: String? = null,
        brokerPort: Int? = null
    ) {
        val current = _config.value
        val updated = current.copy(
            ssid = ssid ?: current.ssid,
            password = password ?: current.password,
            isOpenWifi = isOpenWifi ?: current.isOpenWifi,
            brokerHost = brokerHost ?: current.brokerHost,
            brokerPort = brokerPort ?: current.brokerPort
        )
        _config.value = updated
        _validationResult.value = updated.validate()
    }

    fun proceedToReview(): Boolean {
        val validation = _config.value.validate()
        _validationResult.value = validation
        if (validation.isValid) {
            _currentScreen.value = SetupScreen.REVIEW_SEND
            return true
        }
        return false
    }

    fun sendSettings() {
        _transferErrorReason.value = null
        val success = bleManager.writeProvisioningConfig(_config.value)
        if (!success) {
            _transferSuccess.value = false
            _transferErrorReason.value = bleManager.statusMessage.value
            _currentScreen.value = SetupScreen.RESULT
        }
    }

    fun resetAndConfigureAnother() {
        bleManager.release()
        _targetGatewayName.value = null
        _qrResult.value = null
        _manualDeviceInput.value = ""
        _manualDeviceError.value = null
        _transferSuccess.value = false
        _transferErrorReason.value = null
        _currentScreen.value = SetupScreen.WELCOME
    }

    fun toggleChecklist(show: Boolean) {
        _showChecklistDialog.value = show
    }

    override fun onCleared() {
        super.onCleared()
        bleManager.release()
    }
}
