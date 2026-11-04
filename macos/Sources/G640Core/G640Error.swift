import Foundation

public enum G640Error: LocalizedError, Sendable {
    case profileOpenFailed(String)
    case profileOpenMemoryFailed
    case transformCreationFailed
    case proofingTransformCreationFailed
    case imageLoadFailed(String)
    case imageRenderFailed
    case invalidDimensions(Int, Int)
    case rasterEncodingFailed(String)
    case ippNetworkError(String)
    case cupsSpoolerError(String)

    public var errorDescription: String? {
        switch self {
        case .profileOpenFailed(let path):
            return "Failed to open ICC profile from: \(path)"
        case .profileOpenMemoryFailed:
            return "Failed to parse ICC profile from memory buffer."
        case .transformCreationFailed:
            return "Failed to create LCMS2 color transform."
        case .proofingTransformCreationFailed:
            return "Failed to create LCMS2 proofing transform."
        case .imageLoadFailed(let path):
            return "Failed to load image from: \(path)"
        case .imageRenderFailed:
            return "Failed to render image bitmap buffer."
        case .invalidDimensions(let w, let h):
            return "Invalid image dimensions (\(w)x\(h))."
        case .rasterEncodingFailed(let msg):
            return "Apple Raster URF encoding failed: \(msg)"
        case .ippNetworkError(let msg):
            return "IPP Network error: \(msg)"
        case .cupsSpoolerError(let msg):
            return "CUPS raw spooler error: \(msg)"
        }
    }
}

