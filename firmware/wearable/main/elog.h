#pragma once

/* The wearable's event log for the OLED's log page: the newest ELOG_LINES events, as many as fit
 * on the page, each with its local time. Every event also goes to the serial log.
 *
 * Events: BOOT, ECG ERROR, MODEL ERROR, LEADS OFF / LEADS ON, WIFI CONNECTED / WIFI LOST,
 * CLOCK SYNCED, MQTT CONNECTED / MQTT LOST, NEW SETTINGS, WIFI CLEARED, ABNORMAL S|V SENT|DROP
 * (model alerts), BTN ALERT SENT|DROP. The on-demand ECG commands (Iteration 5, Slice 3) add
 * ECG REQ START / ECG REQ STOP when they are built. */

#include <stddef.h>

#define ELOG_LINES 5   /* DISPLAY_PAGE_LINES */
#define ELOG_TEXT 15   /* characters of text after "HH:MM " on a 21-character line */
#define ELOG_LINE_LEN 22

/* Adds an event; text over ELOG_TEXT characters is cut. Not from an ISR. */
void elog_add(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

/* The events as page lines, newest first: "HH:MM TEXT", or "--:-- TEXT" for an event logged
 * before the clock was set. Returns how many were written (at most max). */
size_t elog_lines(char out[][ELOG_LINE_LEN], size_t max);
