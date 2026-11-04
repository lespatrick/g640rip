import Foundation
import CLcms2

public enum RenderingIntent: UInt32, Sendable {
    case perceptual = 0
    case relativeColorimetric = 1
    case saturation = 2
    case absoluteColorimetric = 3
}

public struct LCMS2Flags: OptionSet, Sendable {
    public let rawValue: UInt32
    public init(rawValue: UInt32) { self.rawValue = rawValue }

    public static let blackPointCompensation = LCMS2Flags(rawValue: 0x2000)
    public static let softProofing           = LCMS2Flags(rawValue: 0x4000)
    public static let gamutCheck             = LCMS2Flags(rawValue: 0x1000)
    public static let noOptimize             = LCMS2Flags(rawValue: 0x0100)
    public static let highQuality            = LCMS2Flags(rawValue: 0x0400)
}

public final class ICCProfile: @unchecked Sendable {
    let handle: cmsHPROFILE

    public init(path: String) throws {
        guard let h = cmsOpenProfileFromFile(path, "r") else {
            throw G640Error.profileOpenFailed(path)
        }
        self.handle = h
    }

    public init(data: Data) throws {
        let handle = data.withUnsafeBytes { buffer -> cmsHPROFILE? in
            guard let base = buffer.baseAddress else { return nil }
            return cmsOpenProfileFromMem(base, UInt32(buffer.count))
        }
        guard let h = handle else {
            throw G640Error.profileOpenMemoryFailed
        }
        self.handle = h
    }

    private init(rawHandle: cmsHPROFILE) {
        self.handle = rawHandle
    }

    public static func sRGB() -> ICCProfile {
        return ICCProfile(rawHandle: cmsCreate_sRGBProfile())
    }

    public static func null() -> ICCProfile {
        return ICCProfile(rawHandle: cmsCreateNULLProfile())
    }

    deinit {
        cmsCloseProfile(handle)
    }
}

public final class ColorTransform: @unchecked Sendable {
    let handle: cmsHTRANSFORM

    public init(
        input: ICCProfile,
        inFormat: UInt32,
        output: ICCProfile,
        outFormat: UInt32,
        intent: RenderingIntent = .relativeColorimetric,
        flags: LCMS2Flags = [.blackPointCompensation, .highQuality]
    ) throws {
        guard let h = cmsCreateTransform(
            input.handle,
            inFormat,
            output.handle,
            outFormat,
            intent.rawValue,
            flags.rawValue
        ) else {
            throw G640Error.transformCreationFailed
        }
        self.handle = h
    }

    public init(
        input: ICCProfile,
        inFormat: UInt32,
        output: ICCProfile,
        outFormat: UInt32,
        proofing: ICCProfile,
        intent: RenderingIntent = .relativeColorimetric,
        proofingIntent: RenderingIntent = .absoluteColorimetric,
        flags: LCMS2Flags = [.softProofing, .blackPointCompensation, .highQuality]
    ) throws {
        guard let h = cmsCreateProofingTransform(
            input.handle,
            inFormat,
            output.handle,
            outFormat,
            proofing.handle,
            intent.rawValue,
            proofingIntent.rawValue,
            flags.rawValue
        ) else {
            throw G640Error.proofingTransformCreationFailed
        }
        self.handle = h
    }

    public func transform(
        input: UnsafeRawPointer,
        output: UnsafeMutableRawPointer,
        pixelCount: Int
    ) {
        cmsDoTransform(handle, input, output, UInt32(pixelCount))
    }

    deinit {
        cmsDeleteTransform(handle)
    }
}

public enum LCMS2PixelFormat {
    public static let rgb8: UInt32   = (4 << 16) | (3 << 3) | 1
    public static let rgba8: UInt32  = (4 << 16) | (1 << 7) | (3 << 3) | 1
    public static let bgr8: UInt32   = (4 << 16) | (3 << 3) | 1 | (1 << 10)
    public static let bgra8: UInt32  = (4 << 16) | (1 << 7) | (3 << 3) | 1 | (1 << 10)
    public static let rgb16: UInt32  = (4 << 16) | (3 << 3) | 2
    public static let rgba16: UInt32 = (4 << 16) | (1 << 7) | (3 << 3) | 2
}
