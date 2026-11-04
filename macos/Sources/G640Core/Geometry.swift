import Foundation
import CoreGraphics

public enum FitMode: String, CaseIterable, Identifiable, Sendable {
    case compensate = "compensate"
    case fill = "fill"
    case fit = "fit"
    case none = "none"

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .compensate: return "Kompensacja bezstratna (Zalecana)"
        case .fill: return "Pełne wypełnienie (Fill / Bleed)"
        case .fit: return "Dopasowanie z marginesami (Fit)"
        case .none: return "Brak skalowania (1:1)"
        }
    }
}

public struct PaperSpec: Sendable, Equatable, Hashable {
    public let name: String
    public let displayName: String
    public let widthMm: Double
    public let heightMm: Double
    public let widthPixels600DPI: Int
    public let heightPixels600DPI: Int
    public let isBorderlessSupported: Bool

    public init(
        name: String,
        displayName: String,
        widthMm: Double,
        heightMm: Double,
        widthPixels600DPI: Int,
        heightPixels600DPI: Int,
        isBorderlessSupported: Bool = true
    ) {
        self.name = name
        self.displayName = displayName
        self.widthMm = widthMm
        self.heightMm = heightMm
        self.widthPixels600DPI = widthPixels600DPI
        self.heightPixels600DPI = heightPixels600DPI
        self.isBorderlessSupported = isBorderlessSupported
    }

    public static let photo4x6 = PaperSpec(
        name: "4x6",
        displayName: "4x6\" / 10x15 cm (PP-201, Luster)",
        widthMm: 101.6,
        heightMm: 152.4,
        widthPixels600DPI: 2400,
        heightPixels600DPI: 3600,
        isBorderlessSupported: true
    )

    public static let a4 = PaperSpec(
        name: "A4",
        displayName: "A4 (210 x 297 mm)",
        widthMm: 210.0,
        heightMm: 297.0,
        widthPixels600DPI: 4960,
        heightPixels600DPI: 7016,
        isBorderlessSupported: true
    )

    public static let standardSizes: [PaperSpec] = [
        .photo4x6,
        .a4
    ]
}

public struct GeometryConfig: Sendable, Equatable {
    public var scaleX: Double        // Default: -1.0% (calibrated width stretch correction)
    public var scaleY: Double        // Default: +0.59% (calibrated roller compression correction)
    public var offsetX: Double       // Default: -0.25% (centering)
    public var offsetY: Double       // Default: -1.59% (feed grab delay)
    public var compY: Double         // Default: 5.0% (bottom roller pinch safety zone)
    public var bleedPct: Double      // Default: 1.5%
    public var fitMode: FitMode      // Default: .compensate
    public var borderless: Bool      // Default: true
    public var autoRotate: Bool      // Default: true

    public init(
        scaleX: Double = -1.0,
        scaleY: Double = 0.59,
        offsetX: Double = -0.25,
        offsetY: Double = -1.59,
        compY: Double = 5.0,
        bleedPct: Double = 1.5,
        fitMode: FitMode = .compensate,
        borderless: Bool = true,
        autoRotate: Bool = true
    ) {
        self.scaleX = scaleX
        self.scaleY = scaleY
        self.offsetX = offsetX
        self.offsetY = offsetY
        self.compY = compY
        self.bleedPct = bleedPct
        self.fitMode = fitMode
        self.borderless = borderless
        self.autoRotate = autoRotate
    }

    public static let calibratedDefault = GeometryConfig()
}
