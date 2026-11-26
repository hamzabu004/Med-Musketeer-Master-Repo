#include "edge_rule.h"

void edge_rule_init(edge_rule_t *r, size_t window, size_t min_abnormal, int64_t cooldown_ms)
{
    r->window = window < 1 ? 1 : window > EDGE_RULE_MAX_WINDOW ? EDGE_RULE_MAX_WINDOW : window;
    r->min_abnormal = min_abnormal < 1 ? 1 : min_abnormal;
    r->cooldown_ms = cooldown_ms;
    r->alerted = false;
    r->last_alert_ms = 0;
    edge_rule_clear(r);
}

void edge_rule_clear(edge_rule_t *r)
{
    r->n = 0;
    r->next = 0;
}

bool edge_rule_push(edge_rule_t *r, int cls, const float probs[3], int64_t now_ms, edge_alert_t *out)
{
    if (cls < 0 || cls > 2) return false;
    r->cls[r->next] = (uint8_t)cls;
    r->prob[r->next] = probs ? probs[cls] : 1.0f;
    r->next = (r->next + 1) % r->window;
    if (r->n < r->window) ++r->n;

    size_t count[3] = {0, 0, 0};
    float sum[3] = {0.0f, 0.0f, 0.0f};
    for (size_t i = 0; i < r->n; ++i) {
        ++count[r->cls[i]];
        sum[r->cls[i]] += r->prob[i];
    }
    const size_t abnormal = count[1] + count[2];
    if (abnormal < r->min_abnormal) return false;
    if (r->alerted && now_ms - r->last_alert_ms < r->cooldown_ms) return false;

    const int label = count[2] >= count[1] ? 2 : 1;
    out->label = label == 2 ? "V" : "S";
    out->confidence = sum[label] / (float)count[label];
    out->abnormal = abnormal;
    r->alerted = true;
    r->last_alert_ms = now_ms;
    return true;
}
