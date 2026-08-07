import 'package:flutter/material.dart';

abstract final class BlissAppTheme {
  static const background = Color(0xfff4f7f3);
  static const surface = Colors.white;
  static const brand = Color(0xff0f766e);
  static const brandDark = Color(0xff115e59);
  static const brandSoft = Color(0xffddf4ee);
  static const teal = Color(0xff0284c7);
  static const amber = Color(0xfff59e0b);
  static const danger = Color(0xffdc2626);
  static const ink = Color(0xff17211b);
  static const muted = Color(0xff66756c);
  static const line = Color(0xffdde6e0);

  static ThemeData light() {
    const scheme = ColorScheme(
      brightness: Brightness.light,
      primary: brand,
      onPrimary: Colors.white,
      primaryContainer: brandSoft,
      onPrimaryContainer: Color(0xff134e4a),
      secondary: teal,
      onSecondary: Colors.white,
      secondaryContainer: Color(0xffd9f7f2),
      onSecondaryContainer: Color(0xff064e47),
      tertiary: amber,
      onTertiary: Color(0xff3b2600),
      tertiaryContainer: Color(0xfffff1ca),
      onTertiaryContainer: Color(0xff5f3d00),
      error: danger,
      onError: Colors.white,
      errorContainer: Color(0xffffe2e2),
      onErrorContainer: Color(0xff7f1d1d),
      surface: surface,
      onSurface: ink,
      onSurfaceVariant: muted,
      outline: Color(0xffb8c7be),
      outlineVariant: line,
      shadow: Color(0x1a0f172a),
      scrim: Color(0x990f172a),
      inverseSurface: Color(0xff1e293b),
      onInverseSurface: Color(0xfff8fafc),
      inversePrimary: Color(0xff99f6e4),
      surfaceTint: Colors.transparent,
    );

    final base = ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      visualDensity: VisualDensity.standard,
    );
    final textTheme = base.textTheme.copyWith(
      headlineLarge: const TextStyle(
        color: ink,
        fontSize: 32,
        height: 1.08,
        fontWeight: FontWeight.w800,
        letterSpacing: -1.1,
      ),
      headlineMedium: const TextStyle(
        color: ink,
        fontSize: 27,
        height: 1.12,
        fontWeight: FontWeight.w800,
        letterSpacing: -.7,
      ),
      headlineSmall: const TextStyle(
        color: ink,
        fontSize: 22,
        height: 1.18,
        fontWeight: FontWeight.w800,
        letterSpacing: -.45,
      ),
      titleLarge: const TextStyle(
        color: ink,
        fontSize: 20,
        height: 1.25,
        fontWeight: FontWeight.w800,
        letterSpacing: -.25,
      ),
      titleMedium: const TextStyle(
        color: ink,
        fontSize: 17,
        height: 1.3,
        fontWeight: FontWeight.w700,
      ),
      bodyLarge: const TextStyle(color: ink, fontSize: 17, height: 1.45),
      bodyMedium: const TextStyle(
        color: Color(0xff45564c),
        fontSize: 16,
        height: 1.45,
      ),
      bodySmall: const TextStyle(color: muted, fontSize: 14, height: 1.4),
      labelLarge: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
      labelMedium: const TextStyle(
        color: muted,
        fontSize: 13,
        fontWeight: FontWeight.w700,
      ),
    );

    return base.copyWith(
      textTheme: textTheme,
      appBarTheme: const AppBarTheme(
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        toolbarHeight: 64,
        backgroundColor: background,
        foregroundColor: ink,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: TextStyle(
          color: brandDark,
          fontSize: 19,
          fontWeight: FontWeight.w900,
          letterSpacing: -.25,
        ),
        iconTheme: IconThemeData(color: ink),
        actionsIconTheme: IconThemeData(color: ink),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: Colors.white,
        surfaceTintColor: Colors.transparent,
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(24),
          side: const BorderSide(color: line),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 18,
        ),
        labelStyle: const TextStyle(color: muted, fontWeight: FontWeight.w600),
        hintStyle: const TextStyle(color: Color(0xff94a3b8)),
        prefixIconColor: const Color(0xff64748b),
        suffixIconColor: const Color(0xff64748b),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: brand, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: danger),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(color: danger, width: 1.5),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 56),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(18),
          ),
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, 54),
          padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 13),
          foregroundColor: brandDark,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(18),
          ),
          side: const BorderSide(color: line),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: brand,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          minimumSize: const Size(48, 48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(15),
          ),
        ),
      ),
      searchBarTheme: SearchBarThemeData(
        elevation: const WidgetStatePropertyAll(0),
        backgroundColor: const WidgetStatePropertyAll(Colors.white),
        surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
        side: const WidgetStatePropertyAll(BorderSide(color: line)),
        shape: WidgetStatePropertyAll(
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        ),
        padding: const WidgetStatePropertyAll(
          EdgeInsets.symmetric(horizontal: 15),
        ),
        hintStyle: const WidgetStatePropertyAll(
          TextStyle(color: muted, fontSize: 16),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: Colors.white,
        selectedColor: brandSoft,
        disabledColor: const Color(0xfff1f5f9),
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
        labelStyle: const TextStyle(
          color: Color(0xff45564c),
          fontSize: 14,
          fontWeight: FontWeight.w700,
        ),
        secondaryLabelStyle: const TextStyle(
          color: brandDark,
          fontSize: 14,
          fontWeight: FontWeight.w800,
        ),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
        side: const BorderSide(color: line),
      ),
      navigationBarTheme: NavigationBarThemeData(
        height: 80,
        elevation: 0,
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        indicatorColor: brandSoft,
        indicatorShape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(15),
        ),
        iconTheme: WidgetStateProperty.resolveWith(
          (states) => IconThemeData(
            color: states.contains(WidgetState.selected) ? brand : muted,
            size: states.contains(WidgetState.selected) ? 28 : 26,
          ),
        ),
        labelTextStyle: WidgetStateProperty.resolveWith(
          (states) => TextStyle(
            color: states.contains(WidgetState.selected) ? brand : muted,
            fontSize: 12,
            fontWeight: states.contains(WidgetState.selected)
                ? FontWeight.w800
                : FontWeight.w600,
          ),
        ),
      ),
      dividerColor: line,
      dividerTheme: const DividerThemeData(color: line, thickness: 1),
      listTileTheme: const ListTileThemeData(
        iconColor: muted,
        textColor: ink,
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 7),
      ),
      dialogTheme: DialogThemeData(
        elevation: 18,
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        showDragHandle: true,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: const Color(0xff1e293b),
        contentTextStyle: const TextStyle(color: Colors.white),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: brand,
        linearTrackColor: brandSoft,
      ),
    );
  }
}
