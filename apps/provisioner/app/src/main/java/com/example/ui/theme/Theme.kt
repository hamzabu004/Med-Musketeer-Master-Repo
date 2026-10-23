package com.example.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

private val DarkColorScheme = darkColorScheme(
    primary = MedTealLight,
    onPrimary = Slate950,
    primaryContainer = Slate800,
    onPrimaryContainer = MedTealLight,
    secondary = MedEmerald,
    onSecondary = Color.Black,
    tertiary = MedAmber,
    background = Slate950,
    onBackground = Slate100,
    surface = Slate900,
    onSurface = Slate100,
    surfaceVariant = Slate800,
    onSurfaceVariant = Slate400,
    outline = Slate700,
    error = MedRed,
    onError = Color.White
)

private val LightColorScheme = lightColorScheme(
    primary = MedTealDark,
    onPrimary = Color.White,
    primaryContainer = Slate100Light,
    onPrimaryContainer = MedTealDark,
    secondary = MedEmeraldDark,
    onSecondary = Color.White,
    tertiary = MedAmber,
    background = Slate50,
    onBackground = Slate900Light,
    surface = Color.White,
    onSurface = Slate900Light,
    surfaceVariant = Slate200,
    onSurfaceVariant = Slate600,
    outline = Slate200,
    error = MedRed,
    onError = Color.White
)

@Composable
fun MedMusketeerTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = false, // Set false to maintain consistent cohesive medical cyber styling
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
