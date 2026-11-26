// ECG beat classifier (N / S / V) for ESP32-S3: TFLite Micro, full INT8.
// From ecg_1dcnn_esp32.zip (model/README.md); changed only to include ecg_classifier.h (C linkage),
// to find the schema header where newer esp-tflite-micro keeps it, and to log the arena use.
// ESP-IDF:  idf.py add-dependency "espressif/esp-tflite-micro"
// Include p1_best_int8_ptq.h in exactly ONE .cpp (it defines the model array).
//
// Usage:
//   ecg_classifier_init();                       // once at boot
//   int cls = ecg_classify_beat(win64, rr4);     // per beat; 0 = N, 1 = S, 2 = V, -1 = error
// win64: 64 ECG samples in mV at 128 Hz, R peak at index 32 (R-32 .. R+31)
// rr4:   {pre/local, pre/global, post/local, post/global} (see README, step 4)

#include <math.h>
#include <stdint.h>

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#if __has_include("tensorflow/lite/micro/schema/schema_generated.h")
#include "tensorflow/lite/micro/schema/schema_generated.h" /* esp-tflite-micro 1.3.4 and later */
#else
#include "tensorflow/lite/schema/schema_generated.h"
#endif

#include "ecg_classifier.h"
#include "esp_log.h"
#include "p1_best_int8_ptq.h"
#include "p1_best_model_meta.h"

static uint8_t tensor_arena[P1_BEST_TENSOR_ARENA_BYTES] __attribute__((aligned(16)));
static tflite::MicroInterpreter* interp = nullptr;

static inline int8_t q8(float x, float scale, int zp) {
    long q = lroundf(x / scale) + zp;
    if (q < -128) q = -128;
    if (q > 127) q = 127;
    return (int8_t)q;
}

bool ecg_classifier_init(void) {
    const tflite::Model* model = tflite::GetModel(p1_best_int8_ptq);
    if (model->version() != TFLITE_SCHEMA_VERSION) return false;

    static tflite::MicroMutableOpResolver<8> resolver;
    resolver.AddConcatenation();
    resolver.AddConv2D();
    resolver.AddFullyConnected();
    resolver.AddQuantize();
    resolver.AddReduceMax();
    resolver.AddReshape();
    resolver.AddSoftmax();
    resolver.AddTanh();

    static tflite::MicroInterpreter static_interp(model, resolver, tensor_arena,
                                                  sizeof(tensor_arena));
    interp = &static_interp;
    if (interp->AllocateTensors() != kTfLiteOk) return false;
    ESP_LOGI("ecg_classifier", "Model loaded; tensor arena %u of %u B used",
             (unsigned)interp->arena_used_bytes(), (unsigned)sizeof(tensor_arena));
    return true;
}

// probs (optional, may be nullptr): receives P(N), P(S), P(V).
int ecg_classify_beat(const float win64[64], const float rr4[4], float probs[3]) {
    if (!interp) return -1;

    // 1) z-score the window
    float mean = 0.f, var = 0.f;
    for (int i = 0; i < 64; ++i) mean += win64[i];
    mean /= 64.f;
    for (int i = 0; i < 64; ++i) { float d = win64[i] - mean; var += d * d; }
    float sd = sqrtf(var / 64.f);
    if (sd <= 1e-9f) sd = 1.f;

    // 2) first difference, last sample repeated: d[i] = x[i+1] - x[i], d[63] = d[62]
    int8_t* ecg = interp->input(P1_BEST_IN_ECG_INDEX)->data.int8;
    float last = 0.f;
    for (int i = 0; i < 63; ++i) {
        last = (win64[i + 1] - win64[i]) / sd;
        ecg[i] = q8(last, P1_BEST_IN_ECG_SCALE, P1_BEST_IN_ECG_ZP);
    }
    ecg[63] = q8(last, P1_BEST_IN_ECG_SCALE, P1_BEST_IN_ECG_ZP);

    // 3) RR features
    int8_t* rr = interp->input(P1_BEST_IN_RR_INDEX)->data.int8;
    for (int j = 0; j < 4; ++j) rr[j] = q8(rr4[j], P1_BEST_IN_RR_SCALE, P1_BEST_IN_RR_ZP);

    if (interp->Invoke() != kTfLiteOk) return -1;

    // 4) argmax over the int8 output (no threshold)
    const int8_t* q = interp->output(0)->data.int8;
    int best = 0;
    for (int k = 1; k < P1_BEST_N_CLASSES; ++k) if (q[k] > q[best]) best = k;
    if (probs) for (int k = 0; k < 3; ++k) probs[k] = (q[k] - P1_BEST_OUT_ZP) * P1_BEST_OUT_SCALE;
    return best;
}
