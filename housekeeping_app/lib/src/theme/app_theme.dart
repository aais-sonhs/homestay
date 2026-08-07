import 'package:flutter/material.dart';

abstract final class BlissAppTheme {
  static const background = Color(0xfff5f7fc);
  static const surface = Colors.white;
  static const brand = Color(0xff4f46e5);
  static const brandDark = Color(0xff3730a3);
  static const teal = Color(0xff0d9488);
  static const amber = Color(0xfff59e0b);
  static const danger = Color(0xffdc2626);
  static const ink = Color(0xff172033);
  static const muted = Color(0xff64748b);
  static const line = Color(0xffe6eaf2);

  static ThemeData light() {
    const scheme = ColorScheme(
      brightness: Brightness.light,
      primary: brand,
      onPrimary: Colors.white,
      primaryContainer: Color(0xffe9e8ff),
      onPrimaryContainer: Color(0xff27206f),
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
      outline: Color(0xffcbd2df),
      outlineVariant: line,
      shadow: Color(0x1a0f172a),
      scrim: Color(0x990f172a),
      inverseSurface: Color(0xff1e293b),
      onInverseSurface: Color(0xfff8fafc),
      inversePrimary: Color(0xffc7d2fe),
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
        fontSize: 34,
        height: 1.08,
        fontWeight: FontWeight.w800,
        letterSpacing: -1.1,
      ),
      headlineMedium: const TextStyle(
        color: ink,
        fontSize: 28,
        height: 1.12,
        fontWeight: FontWeight.w800,
        letterSpacing: -.7,
      ),
      headlineSmall: const TextStyle(
        color: ink,
        fontSize: 23,
        height: 1.18,
        fontWeight: FontWeight.w800,
        letterSpacing: -.45,
      ),
      titleLarge: const TextStyle(
        color: ink,
        fontSize: 19,
        height: 1.25,
        fontWeight: FontWeight.w800,
        letterSpacing: -.25,
      ),
      titleMedium: const TextStyle(
        color: ink,
        fontSize: 15,
        height: 1.3,
        fontWeight: FontWeight.w700,
      ),
      bodyLarge: const TextStyle(color: ink, fontSize: 15, height: 1.5),
      bodyMedium: const TextStyle(
        color: Color(0xff475569),
        fontSize: 14,
        height: 1.5,
      ),
      bodySmall: const TextStyle(color: muted, fontSize: 12, height: 1.45),
      labelLarge: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
      labelMedium: const TextStyle(
        color: muted,
        fontSize: 11,
        fontWeight: FontWeight.w700,
      ),
    );

    return base.copyWith(
      textTheme: textTheme,
      appBarTheme: const AppBarTheme(
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        toolbarHeight: 68,
        backgroundColor: Colors.white,
        foregroundColor: ink,
        surfaceTintColor: Colors.transparent,
        shape: Border(bottom: BorderSide(color: line)),
        titleTextStyle: TextStyle(
          color: ink,
          fontSize: 18,
          fontWeight: FontWeight.w800,
          letterSpacing: -.25,
        ),
        iconTheme: IconThemeData(color: Color(0xff475569)),
        actionsIconTheme: IconThemeData(color: Color(0xff475569)),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: Colors.white,
        surfaceTintColor: Colors.transparent,
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: const BorderSide(color: line),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xfff8fafc),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 16,
        ),
        labelStyle: const TextStyle(color: muted, fontWeight: FontWeight.w600),
        hintStyle: const TextStyle(color: Color(0xff94a3b8)),
        prefixIconColor: const Color(0xff64748b),
        suffixIconColor: const Color(0xff64748b),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: brand, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: danger),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: danger, width: 1.5),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 52),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, 50),
          padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 13),
          foregroundColor: const Color(0xff475569),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          side: const BorderSide(color: line),
          textStyle: const TextStyle(fontWeight: FontWeight.w800),
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
          minimumSize: const Size(42, 42),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(13),
          ),
        ),
      ),
      searchBarTheme: SearchBarThemeData(
        elevation: const WidgetStatePropertyAll(0),
        backgroundColor: const WidgetStatePropertyAll(Colors.white),
        surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
        side: const WidgetStatePropertyAll(BorderSide(color: line)),
        shape: WidgetStatePropertyAll(
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(17)),
        ),
        padding: const WidgetStatePropertyAll(
          EdgeInsets.symmetric(horizontal: 15),
        ),
        hintStyle: const WidgetStatePropertyAll(
          TextStyle(color: Color(0xff94a3b8), fontSize: 14),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: Colors.white,
        selectedColor: const Color(0xffe9e8ff),
        disabledColor: const Color(0xfff1f5f9),
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
        labelStyle: const TextStyle(
          color: Color(0xff475569),
          fontSize: 12,
          fontWeight: FontWeight.w700,
        ),
        secondaryLabelStyle: const TextStyle(
          color: brandDark,
          fontSize: 12,
          fontWeight: FontWeight.w800,
        ),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
        side: const BorderSide(color: line),
      ),
      navigationBarTheme: NavigationBarThemeData(
        height: 76,
        elevation: 8,
        shadowColor: const Color(0x260f172a),
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        indicatorColor: const Color(0xffe9e8ff),
        indicatorShape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(15),
        ),
        iconTheme: WidgetStateProperty.resolveWith(
          (states) => IconThemeData(
            color: states.contains(WidgetState.selected) ? brand : muted,
            size: states.contains(WidgetState.selected) ? 25 : 23,
          ),
        ),
        labelTextStyle: WidgetStateProperty.resolveWith(
          (states) => TextStyle(
            color: states.contains(WidgetState.selected) ? brand : muted,
            fontSize: 11,
            fontWeight: states.contains(WidgetState.selected)
                ? FontWeight.w800
                : FontWeight.w600,
          ),
        ),
      ),
      dividerColor: line,
      dividerTheme: const DividerThemeData(color: line, thickness: 1),
      listTileTheme: const ListTileThemeData(
        iconColor: Color(0xff64748b),
        textColor: ink,
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
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
        linearTrackColor: Color(0xffe9e8ff),
      ),
    );
  }
}
