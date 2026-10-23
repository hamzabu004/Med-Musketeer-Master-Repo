package com.example.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.util.Log
import com.example.model.ConnectionStage
import com.example.model.GatewayDevice
import com.example.model.ProvisioningConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.Locale

class BleManager(private val context: Context) {

    private val tag = "MedMusketeerBle"
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val bluetoothManager: BluetoothManager? by lazy {
        context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
    }
    private val bluetoothAdapter: BluetoothAdapter? by lazy {
        bluetoothManager?.adapter
    }

    // Scanned devices map (keyed by MAC address)
    private val _scannedDevices = MutableStateFlow<List<GatewayDevice>>(emptyList())
    val scannedDevices: StateFlow<List<GatewayDevice>> = _scannedDevices.asStateFlow()

    // Current connection stage
    private val _connectionStage = MutableStateFlow(ConnectionStage.IDLE)
    val connectionStage: StateFlow<ConnectionStage> = _connectionStage.asStateFlow()

    // Currently connected/selected device
    private val _connectedDevice = MutableStateFlow<GatewayDevice?>(null)
    val connectedDevice: StateFlow<GatewayDevice?> = _connectedDevice.asStateFlow()

    // Current negotiated MTU
    private val _currentMtu = MutableStateFlow(23)
    val currentMtu: StateFlow<Int> = _currentMtu.asStateFlow()

    // Detailed status / error message
    private val _statusMessage = MutableStateFlow<String>("")
    val statusMessage: StateFlow<String> = _statusMessage.asStateFlow()

    // One-shot events
    private val _eventFlow = MutableSharedFlow<BleEvent>()
    val eventFlow: SharedFlow<BleEvent> = _eventFlow.asSharedFlow()

    private var activeGatt: BluetoothGatt? = null
    private var configCharacteristic: BluetoothGattCharacteristic? = null
    private var targetDeviceName: String? = null

    private var isScanning = false
    private var scanTimeoutJob: Job? = null
    private var connectionTimeoutJob: Job? = null

    private var isReceiverRegistered = false

    // Broadcast receiver for bonding changes
    private val bondStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(c: Context?, intent: Intent?) {
            if (intent?.action == BluetoothDevice.ACTION_BOND_STATE_CHANGED) {
                val device = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE)
                }

                val currentDevice = _connectedDevice.value?.bluetoothDevice
                if (device == null || currentDevice == null || device.address != currentDevice.address) {
                    return
                }

                val bondState = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.BOND_NONE)
                val prevBondState = intent.getIntExtra(BluetoothDevice.EXTRA_PREVIOUS_BOND_STATE, BluetoothDevice.BOND_NONE)

                Log.d(tag, "Bond state changed: $prevBondState -> $bondState for ${device.address}")

                when (bondState) {
                    BluetoothDevice.BOND_BONDED -> {
                        _statusMessage.value = "Secure bonding complete (MITM authenticated)"
                        _connectionStage.value = ConnectionStage.BONDED
                        scope.launch {
                            _eventFlow.emit(BleEvent.BondingSuccess)
                        }
                    }
                    BluetoothDevice.BOND_BONDING -> {
                        _statusMessage.value = "Pairing with gateway. Please enter the passkey from the gateway OLED."
                        _connectionStage.value = ConnectionStage.WAITING_FOR_BONDING
                    }
                    BluetoothDevice.BOND_NONE -> {
                        if (prevBondState == BluetoothDevice.BOND_BONDING) {
                            _statusMessage.value = "Pairing failed or cancelled. Verify passkey on gateway OLED."
                            _connectionStage.value = ConnectionStage.FAILED
                            scope.launch {
                                _eventFlow.emit(BleEvent.BondingFailed("Pairing was rejected or cancelled. Check the OLED passkey and retry."))
                            }
                        }
                    }
                }
            }
        }
    }

    private val scanCallback = object : ScanCallback() {
        @SuppressLint("MissingPermission")
        override fun onScanResult(callbackType: Int, result: ScanResult?) {
            result ?: return
            val device = result.device ?: return
            val name = result.scanRecord?.deviceName ?: device.name ?: return

            // Match MedMusketeer gateway naming format: MM-GW-XXXXXX
            if (BleConstants.DEVICE_NAME_REGEX.matches(name)) {
                val currentTarget = targetDeviceName
                val isExactMatch = currentTarget != null && name.equals(currentTarget, ignoreCase = true)

                val gatewayDevice = GatewayDevice(
                    name = name,
                    address = device.address,
                    rssi = result.rssi,
                    bluetoothDevice = device,
                    lastSeenTimestamp = System.currentTimeMillis()
                )

                updateDiscoveredDevice(gatewayDevice)

                if (isExactMatch && _connectionStage.value == ConnectionStage.SCANNING) {
                    _connectionStage.value = ConnectionStage.DEVICE_FOUND
                    _statusMessage.value = "Found target gateway: $name ($device.address)"
                }
            }
        }

        override fun onScanFailed(errorCode: Int) {
            isScanning = false
            _statusMessage.value = "BLE scan failed with code: $errorCode"
            _connectionStage.value = ConnectionStage.FAILED
            scope.launch {
                _eventFlow.emit(BleEvent.Error("Scan failed (error code $errorCode). Check Bluetooth."))
            }
        }
    }

    private val gattCallback = object : BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(gatt: BluetoothGatt?, status: Int, newState: Int) {
            Log.d(tag, "onConnectionStateChange: status=$status, newState=$newState")
            connectionTimeoutJob?.cancel()

            if (status != BluetoothGatt.GATT_SUCCESS) {
                val errMsg = parseGattStatus(status)
                _statusMessage.value = "Connection error: $errMsg"
                _connectionStage.value = ConnectionStage.FAILED
                scope.launch {
                    _eventFlow.emit(BleEvent.Error("GATT connection failed ($errMsg). Status code: $status"))
                }
                disconnectAndClose()
                return
            }

            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    _statusMessage.value = "Connected to gateway. Requesting MTU 517..."
                    _connectionStage.value = ConnectionStage.REQUESTING_MTU
                    // Negotiate MTU 517 as required by firmware contract
                    scope.launch {
                        delay(300)
                        gatt?.requestMtu(BleConstants.REQUESTED_MTU)
                    }
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    _statusMessage.value = "Disconnected from gateway"
                    if (_connectionStage.value != ConnectionStage.WRITE_SUCCESS) {
                        _connectionStage.value = ConnectionStage.FAILED
                    }
                    disconnectAndClose()
                }
            }
        }

        @SuppressLint("MissingPermission")
        override fun onMtuChanged(gatt: BluetoothGatt?, mtu: Int, status: Int) {
            Log.d(tag, "onMtuChanged: mtu=$mtu, status=$status")
            _currentMtu.value = mtu
            if (status == BluetoothGatt.GATT_SUCCESS) {
                _statusMessage.value = "MTU negotiated: $mtu bytes. Discovering services..."
            } else {
                _statusMessage.value = "MTU request returned status $status. Discovering services..."
            }
            _connectionStage.value = ConnectionStage.DISCOVERING_SERVICES

            scope.launch {
                delay(300)
                gatt?.discoverServices()
            }
        }

        @SuppressLint("MissingPermission")
        override fun onServicesDiscovered(gatt: BluetoothGatt?, status: Int) {
            Log.d(tag, "onServicesDiscovered: status=$status")
            if (status != BluetoothGatt.GATT_SUCCESS) {
                _statusMessage.value = "Service discovery failed with status $status"
                _connectionStage.value = ConnectionStage.FAILED
                return
            }

            val service = gatt?.getService(BleConstants.SERVICE_UUID)
            if (service == null) {
                _statusMessage.value = "Provisioning service (${BleConstants.SERVICE_UUID}) not found on gateway!"
                _connectionStage.value = ConnectionStage.FAILED
                scope.launch {
                    _eventFlow.emit(BleEvent.Error("Gateway does not expose expected provisioning service"))
                }
                return
            }

            val char = service.getCharacteristic(BleConstants.CONFIG_CHAR_UUID)
            if (char == null) {
                _statusMessage.value = "Configuration characteristic (${BleConstants.CONFIG_CHAR_UUID}) not found!"
                _connectionStage.value = ConnectionStage.FAILED
                scope.launch {
                    _eventFlow.emit(BleEvent.Error("Provisioning characteristic not found on gateway"))
                }
                return
            }

            configCharacteristic = char
            val device = gatt.device

            // Inspect bonding state
            when (device?.bondState) {
                BluetoothDevice.BOND_BONDED -> {
                    _statusMessage.value = "Gateway bonded and ready for configuration."
                    _connectionStage.value = ConnectionStage.BONDED
                }
                BluetoothDevice.BOND_BONDING -> {
                    _statusMessage.value = "Pairing in progress. Please enter the passkey from gateway OLED."
                    _connectionStage.value = ConnectionStage.WAITING_FOR_BONDING
                }
                else -> {
                    _statusMessage.value = "Pairing required. Triggering bonding..."
                    _connectionStage.value = ConnectionStage.WAITING_FOR_BONDING
                    scope.launch {
                        delay(200)
                        device?.createBond()
                    }
                }
            }
        }

        override fun onCharacteristicWrite(
            gatt: BluetoothGatt?,
            characteristic: BluetoothGattCharacteristic?,
            status: Int
        ) {
            Log.d(tag, "onCharacteristicWrite: status=$status, uuid=${characteristic?.uuid}")
            if (status == BluetoothGatt.GATT_SUCCESS) {
                _statusMessage.value = "Settings accepted by gateway!"
                _connectionStage.value = ConnectionStage.WRITE_SUCCESS
                scope.launch {
                    _eventFlow.emit(BleEvent.WriteSuccess)
                }
            } else {
                val errorDesc = parseGattStatus(status)
                _statusMessage.value = "Write rejected by gateway ($errorDesc, code: $status)"
                _connectionStage.value = ConnectionStage.FAILED
                scope.launch {
                    _eventFlow.emit(BleEvent.WriteFailed("Write failed: $errorDesc (GATT $status)"))
                }
            }
        }
    }

    private fun registerReceiverIfNeeded() {
        if (!isReceiverRegistered) {
            val filter = IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED)
            context.registerReceiver(bondStateReceiver, filter)
            isReceiverRegistered = true
        }
    }

    private fun unregisterReceiverIfNeeded() {
        if (isReceiverRegistered) {
            try {
                context.unregisterReceiver(bondStateReceiver)
            } catch (_: Exception) {}
            isReceiverRegistered = false
        }
    }

    private fun updateDiscoveredDevice(device: GatewayDevice) {
        val currentList = _scannedDevices.value.toMutableList()
        val index = currentList.indexOfFirst { it.address == device.address }
        if (index >= 0) {
            currentList[index] = device
        } else {
            currentList.add(device)
        }
        _scannedDevices.value = currentList.sortedByDescending { it.rssi }
    }

    @SuppressLint("MissingPermission")
    fun startActiveScan(targetName: String? = null) {
        val adapter = bluetoothAdapter
        if (adapter == null || !adapter.isEnabled) {
            _statusMessage.value = "Bluetooth is disabled. Please enable Bluetooth."
            _connectionStage.value = ConnectionStage.FAILED
            scope.launch {
                _eventFlow.emit(BleEvent.Error("Bluetooth is turned off"))
            }
            return
        }

        stopScan()
        _scannedDevices.value = emptyList()
        targetDeviceName = targetName?.uppercase(Locale.ROOT)
        _connectionStage.value = ConnectionStage.SCANNING
        _statusMessage.value = if (targetDeviceName != null) {
            "Active scanning for gateway $targetDeviceName..."
        } else {
            "Active scanning for MedMusketeer gateways (MM-GW-*)..."
        }

        registerReceiverIfNeeded()

        val scanner = adapter.bluetoothLeScanner
        if (scanner == null) {
            _statusMessage.value = "BLE scanner unavailable"
            _connectionStage.value = ConnectionStage.FAILED
            return
        }

        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .setReportDelay(0)
            .build()

        try {
            scanner.startScan(null, settings, scanCallback)
            isScanning = true
        } catch (e: SecurityException) {
            _statusMessage.value = "Bluetooth scan permission denied"
            _connectionStage.value = ConnectionStage.FAILED
            return
        } catch (e: Exception) {
            _statusMessage.value = "Error starting scan: ${e.message}"
            _connectionStage.value = ConnectionStage.FAILED
            return
        }

        scanTimeoutJob?.cancel()
        scanTimeoutJob = scope.launch {
            delay(BleConstants.SCAN_TIMEOUT_MS)
            if (isScanning) {
                stopScan()
                if (_scannedDevices.value.isEmpty()) {
                    _statusMessage.value = "No MedMusketeer gateway found within timeout."
                    _connectionStage.value = ConnectionStage.FAILED
                    _eventFlow.emit(BleEvent.ScanTimeout)
                }
            }
        }
    }

    @SuppressLint("MissingPermission")
    fun stopScan() {
        scanTimeoutJob?.cancel()
        if (isScanning) {
            try {
                bluetoothAdapter?.bluetoothLeScanner?.stopScan(scanCallback)
            } catch (_: Exception) {}
            isScanning = false
        }
    }

    @SuppressLint("MissingPermission")
    fun connectToDevice(device: GatewayDevice) {
        stopScan()
        disconnectAndClose()
        registerReceiverIfNeeded()

        _connectedDevice.value = device
        _connectionStage.value = ConnectionStage.CONNECTING_GATT
        _statusMessage.value = "Connecting to ${device.name} (${device.address})..."

        val btDevice = device.bluetoothDevice ?: bluetoothAdapter?.getRemoteDevice(device.address)
        if (btDevice == null) {
            _statusMessage.value = "Invalid Bluetooth device handle"
            _connectionStage.value = ConnectionStage.FAILED
            return
        }

        connectionTimeoutJob?.cancel()
        connectionTimeoutJob = scope.launch {
            delay(BleConstants.CONNECTION_TIMEOUT_MS)
            if (_connectionStage.value == ConnectionStage.CONNECTING_GATT) {
                _statusMessage.value = "Connection timed out. Check gateway power and proximity."
                _connectionStage.value = ConnectionStage.FAILED
                disconnectAndClose()
                _eventFlow.emit(BleEvent.Error("Connection timed out. Gateway may be out of range."))
            }
        }

        activeGatt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            btDevice.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
        } else {
            btDevice.connectGatt(context, false, gattCallback)
        }
    }

    @SuppressLint("MissingPermission")
    fun initiateBonding() {
        val device = _connectedDevice.value?.bluetoothDevice
        if (device == null) {
            _statusMessage.value = "No device connected to initiate bonding"
            return
        }
        _statusMessage.value = "Initiating pairing. Enter passkey shown on gateway OLED."
        _connectionStage.value = ConnectionStage.WAITING_FOR_BONDING
        device.createBond()
    }

    @SuppressLint("MissingPermission")
    fun writeProvisioningConfig(config: ProvisioningConfig): Boolean {
        val gatt = activeGatt
        val char = configCharacteristic

        if (gatt == null || char == null) {
            _statusMessage.value = "Cannot write: not connected to gateway characteristic"
            _connectionStage.value = ConnectionStage.FAILED
            return false
        }

        val validation = config.validate()
        if (!validation.isValid) {
            _statusMessage.value = "Validation failed: ${validation.error}"
            return false
        }

        val jsonPayload = config.toJsonPayload()
        val payloadBytes = jsonPayload.toByteArray(Charsets.UTF_8)

        if (payloadBytes.size > BleConstants.MAX_PAYLOAD_BYTES) {
            _statusMessage.value = "Payload too large (${payloadBytes.size} bytes). Max is ${BleConstants.MAX_PAYLOAD_BYTES} bytes."
            _connectionStage.value = ConnectionStage.FAILED
            return false
        }

        _connectionStage.value = ConnectionStage.WRITING_CONFIG
        _statusMessage.value = "Sending provisioning payload (${payloadBytes.size} bytes) via GATT write with response..."

        return try {
            val success = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val writeResult = gatt.writeCharacteristic(
                    char,
                    payloadBytes,
                    BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                )
                writeResult == BluetoothStatusCodes.SUCCESS
            } else {
                @Suppress("DEPRECATION")
                char.value = payloadBytes
                char.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                @Suppress("DEPRECATION")
                gatt.writeCharacteristic(char)
            }

            if (!success) {
                _statusMessage.value = "Failed to initiate GATT write to gateway."
                _connectionStage.value = ConnectionStage.FAILED
            }
            success
        } catch (e: Exception) {
            _statusMessage.value = "Write exception: ${e.message}"
            _connectionStage.value = ConnectionStage.FAILED
            false
        }
    }

    @SuppressLint("MissingPermission")
    fun disconnectAndClose() {
        connectionTimeoutJob?.cancel()
        try {
            activeGatt?.disconnect()
            activeGatt?.close()
        } catch (_: Exception) {}
        activeGatt = null
        configCharacteristic = null
    }

    fun release() {
        stopScan()
        disconnectAndClose()
        unregisterReceiverIfNeeded()
        _connectionStage.value = ConnectionStage.IDLE
        _connectedDevice.value = null
        _scannedDevices.value = emptyList()
    }

    fun isBluetoothEnabled(): Boolean {
        return bluetoothAdapter?.isEnabled == true
    }

    private fun parseGattStatus(status: Int): String {
        return when (status) {
            BluetoothGatt.GATT_SUCCESS -> "Success"
            BluetoothGatt.GATT_READ_NOT_PERMITTED -> "Read not permitted"
            BluetoothGatt.GATT_WRITE_NOT_PERMITTED -> "Write not permitted"
            BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION -> "Insufficient authentication (Bonding required)"
            BluetoothGatt.GATT_INSUFFICIENT_ENCRYPTION -> "Insufficient encryption (MITM pairing required)"
            BluetoothGatt.GATT_INVALID_OFFSET -> "Invalid offset"
            BluetoothGatt.GATT_INVALID_ATTRIBUTE_LENGTH -> "Invalid attribute length"
            133 -> "GATT error 133 (Device busy / connection dropped)"
            else -> "GATT status $status"
        }
    }
}

// Sealed class for BleEvents
sealed class BleEvent {
    data object BondingSuccess : BleEvent()
    data class BondingFailed(val reason: String) : BleEvent()
    data object WriteSuccess : BleEvent()
    data class WriteFailed(val reason: String) : BleEvent()
    data object ScanTimeout : BleEvent()
    data class Error(val message: String) : BleEvent()
}
