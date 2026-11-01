---
description: Odpytaj drukarkę Canon G640 po IPP i wygeneruj strukturę strumienia URF/PWG
---
1. Użyj narzędzia `ipptool` w terminalu, aby pobrać pełną listę `urf-supported` oraz `pwg-raster-document-type-supported` z drukarki Canon G640 w sieci lokalnej lub na USB.
2. Przeanalizuj obsługiwane rozdzielczości (600dpi, 1200dpi), głębię bitową i przestrzenie barw (`srgb_8`, `adobe-rgb_16`, `cmyk_8`).
3. Napisz moduł pakujący 16-bitowy bufor po konwersji LittleCMS2 w bezstratny strumień PWG/URF Raster i wysyłający go bezpośrednio na socket IPP drukarki z flagą wyłączającą optymalizację obrazu.
