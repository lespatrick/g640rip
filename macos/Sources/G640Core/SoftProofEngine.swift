import Foundation
import CoreGraphics
import CLcms2

public final class SoftProofEngine: Sendable {
    public init() {}

    /// Generates a soft-proofed CGImage simulating paper white/ink and an optional neon out-of-gamut mask.
    public static func renderSoftProof(
        image: CGImage,
        paperProfile: ICCProfile,
        displayProfile: ICCProfile? = nil,
        simulatePaperWhite: Bool = false,
        highlightGamutAlarm: Bool = true
    ) throws -> (proofImage: CGImage, gamutMaskImage: CGImage?) {
        let width = image.width
        let height = image.height
        let pixelCount = width * height

        // 1. Render input CGImage to 8-bit RGBA bitmap
        let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
        let bytesPerRow = width * 4
        var inputBuffer = Data(count: height * bytesPerRow)

        let rendered = inputBuffer.withUnsafeMutableBytes { bytes -> Bool in
            guard let baseAddr = bytes.baseAddress else { return false }
            guard let ctx = CGContext(
                data: baseAddr,
                width: width,
                height: height,
                bitsPerComponent: 8,
                bytesPerRow: bytesPerRow,
                space: colorSpace,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }

            ctx.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }

        guard rendered else {
            throw G640Error.imageRenderFailed
        }

        // 2. Prepare LittleCMS2 Proofing Transform
        let dispProfile = displayProfile ?? ICCProfile.sRGB()
        let inProfile = ICCProfile.sRGB()

        let proofIntent: RenderingIntent = simulatePaperWhite ? .absoluteColorimetric : .relativeColorimetric
        var flags: LCMS2Flags = [.softProofing, .blackPointCompensation, .highQuality]
        if highlightGamutAlarm {
            flags.insert(.gamutCheck)
            // Set alarm codes to neon magenta: R=0xFFFF, G=0x0000, B=0xFFFF
            var alarmCodes: [UInt16] = [0xFFFF, 0x0000, 0xFFFF, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            cmsSetAlarmCodes(&alarmCodes)
        }

        let transform = try ColorTransform(
            input: inProfile,
            inFormat: LCMS2PixelFormat.rgba8,
            output: dispProfile,
            outFormat: LCMS2PixelFormat.rgba8,
            proofing: paperProfile,
            intent: .relativeColorimetric,
            proofingIntent: proofIntent,
            flags: flags
        )

        var proofBuffer = Data(count: height * bytesPerRow)
        var gamutMaskBuffer = highlightGamutAlarm ? Data(count: height * bytesPerRow) : nil

        inputBuffer.withUnsafeBytes { inBytes in
            proofBuffer.withUnsafeMutableBytes { outBytes in
                guard let inPtr = inBytes.baseAddress,
                      let outPtr = outBytes.baseAddress else { return }
                transform.transform(input: inPtr, output: outPtr, pixelCount: pixelCount)
            }
        }

        // Extract gamut mask if alarm was enabled
        if highlightGamutAlarm {
            var maskData = Data(count: height * bytesPerRow)
            proofBuffer.withUnsafeBytes { proofBytes in
                maskData.withUnsafeMutableBytes { maskBytes in
                    guard let pIn = proofBytes.baseAddress?.assumingMemoryBound(to: UInt8.self),
                          let pMask = maskBytes.baseAddress?.assumingMemoryBound(to: UInt8.self) else { return }

                    for i in 0..<pixelCount {
                        let r = pIn[i * 4 + 0]
                        let g = pIn[i * 4 + 1]
                        let b = pIn[i * 4 + 2]

                        // Neon alarm code check: R > 250, G < 10, B > 250
                        if r >= 250 && g <= 10 && b >= 250 {
                            pMask[i * 4 + 0] = 255 // R
                            pMask[i * 4 + 1] = 0   // G
                            pMask[i * 4 + 2] = 255 // B
                            pMask[i * 4 + 3] = 255 // A
                        } else {
                            pMask[i * 4 + 0] = 0
                            pMask[i * 4 + 1] = 0
                            pMask[i * 4 + 2] = 0
                            pMask[i * 4 + 3] = 0
                        }
                    }
                }
            }
            gamutMaskBuffer = maskData
        }

        // 3. Create resulting CGImages
        guard let proofCg = createCGImage(data: proofBuffer, width: width, height: height, colorSpace: colorSpace) else {
            throw G640Error.imageRenderFailed
        }

        var maskCg: CGImage? = nil
        if let maskBuf = gamutMaskBuffer {
            maskCg = createCGImage(data: maskBuf, width: width, height: height, colorSpace: colorSpace)
        }

        return (proofCg, maskCg)
    }

    private static func createCGImage(data: Data, width: Int, height: Int, colorSpace: CGColorSpace) -> CGImage? {
        guard let provider = CGDataProvider(data: data as CFData) else { return nil }
        return CGImage(
            width: width,
            height: height,
            bitsPerComponent: 8,
            bitsPerPixel: 32,
            bytesPerRow: width * 4,
            space: colorSpace,
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
            provider: provider,
            decode: nil,
            shouldInterpolate: true,
            intent: .defaultIntent
        )
    }
}
