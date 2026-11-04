import Foundation
import CoreGraphics
import ImageIO
import Accelerate

public final class ColorEngine: Sendable {
    public let paperProfile: ICCProfile?
    public let maxInkTotal: Double

    public init(paperProfile: ICCProfile? = nil, maxInkTotal: Double = 1.0) {
        self.paperProfile = paperProfile
        self.maxInkTotal = max(0.1, min(1.0, maxInkTotal))
    }

    /// Loads an image from URL and extracts its CGImage and optional embedded ICC profile data.
    public static func loadImage(from url: URL) throws -> (image: CGImage, embeddedProfile: ICCProfile?) {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else {
            throw G640Error.imageLoadFailed(url.path)
        }
        guard let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            throw G640Error.imageLoadFailed(url.path)
        }

        var profile: ICCProfile? = nil
        if let cs = cgImage.colorSpace, let cfData = cs.copyICCData() {
            profile = try? ICCProfile(data: cfData as Data)
        }
        return (cgImage, profile)
    }

    /// Performs the complete 16-bit layout, color transform, and geometry alignment for photographic printing.
    /// Returns 24-bit RGB bitmap buffer ready for AppleRasterEncoder.
    public func processForPrint(
        image: CGImage,
        inputProfile: ICCProfile?,
        paper: PaperSpec,
        config: GeometryConfig,
        dpi: Int = 600
    ) throws -> (buffer: Data, width: Int, height: Int) {
        let canvasW = paper.widthPixels600DPI
        let canvasH = paper.heightPixels600DPI

        // 1. Layout & Geometric Rendering to 16-bit RGBA Canvas
        let (raw16Data, finalW, finalH) = try renderLayout16Bit(
            sourceImage: image,
            canvasW: canvasW,
            canvasH: canvasH,
            config: config
        )

        // 2. Color Transformation via LittleCMS2
        let inProfile = inputProfile ?? ICCProfile.sRGB()
        let outProfile = paperProfile ?? ICCProfile.sRGB()

        let transform = try ColorTransform(
            input: inProfile,
            inFormat: LCMS2PixelFormat.rgba16,
            output: outProfile,
            outFormat: LCMS2PixelFormat.rgb16,
            intent: .relativeColorimetric,
            flags: [.blackPointCompensation, .highQuality]
        )

        let pixelCount = finalW * finalH
        var out16Buffer = Data(count: pixelCount * 6) // 3 channels * 2 bytes = 6 bytes

        raw16Data.withUnsafeBytes { inBytes in
            out16Buffer.withUnsafeMutableBytes { outBytes in
                guard let inPtr = inBytes.baseAddress,
                      let outPtr = outBytes.baseAddress else { return }
                transform.transform(input: inPtr, output: outPtr, pixelCount: pixelCount)
            }
        }

        // 3. Convert 16-bit device RGB to 8-bit RGB with optional Ink Limiter
        var out8Buffer = Data(count: pixelCount * 3)
        let inkLimitFactor = self.maxInkTotal

        out16Buffer.withUnsafeBytes { in16Bytes in
            out8Buffer.withUnsafeMutableBytes { out8Bytes in
                guard let in16 = in16Bytes.baseAddress?.assumingMemoryBound(to: UInt16.self),
                      let out8 = out8Bytes.baseAddress?.assumingMemoryBound(to: UInt8.self) else { return }

                for i in 0..<pixelCount {
                    let r16 = Double(in16[i * 3 + 0]) / 65535.0
                    let g16 = Double(in16[i * 3 + 1]) / 65535.0
                    let b16 = Double(in16[i * 3 + 2]) / 65535.0

                    var r = r16
                    var g = g16
                    var b = b16

                    // Ink limiter: clamp CMYK density / total ink coverage
                    if inkLimitFactor < 0.999 {
                        // Total ink estimate in inverted space (1 - RGB)
                        let ink = (1.0 - r) + (1.0 - g) + (1.0 - b)
                        let maxAllowed = 3.0 * inkLimitFactor
                        if ink > maxAllowed {
                            let scale = maxAllowed / ink
                            r = 1.0 - (1.0 - r) * scale
                            g = 1.0 - (1.0 - g) * scale
                            b = 1.0 - (1.0 - b) * scale
                        }
                    }

                    out8[i * 3 + 0] = UInt8(clamping: Int(round(r * 255.0)))
                    out8[i * 3 + 1] = UInt8(clamping: Int(round(g * 255.0)))
                    out8[i * 3 + 2] = UInt8(clamping: Int(round(b * 255.0)))
                }
            }
        }

        return (out8Buffer, finalW, finalH)
    }

    /// Layout calculation and rasterization to 16-bit RGBA buffer with hardware scaling & offsets.
    private func renderLayout16Bit(
        sourceImage: CGImage,
        canvasW: Int,
        canvasH: Int,
        config: GeometryConfig
    ) throws -> (data: Data, width: Int, height: Int) {
        var srcImg = sourceImage
        var imgW = srcImg.width
        var imgH = srcImg.height

        // Auto-rotate if orientations mismatch
        if config.autoRotate {
            let canvasIsPortrait = canvasH >= canvasW
            let imgIsPortrait = imgH >= imgW
            if canvasIsPortrait != imgIsPortrait {
                if let rotated = rotateImage90CW(srcImg) {
                    srcImg = rotated
                    imgW = srcImg.width
                    imgH = srcImg.height
                }
            }
        }

        let scaleXFactor = 1.0 + (config.scaleX / 100.0)
        let scaleYFactor = 1.0 + (config.scaleY / 100.0)

        // Calculate source placement rect and safe margins based on FitMode
        let destRect: CGRect
        let canvasRect = CGRect(x: 0, y: 0, width: canvasW, height: canvasH)

        switch config.fitMode {
        case .none:
            let scaledW = Double(imgW) * scaleXFactor
            let scaledH = Double(imgH) * scaleYFactor
            let shiftX = (config.offsetX / 100.0) * Double(canvasW)
            let shiftY = (config.offsetY / 100.0) * Double(canvasH)
            let posX = (Double(canvasW) - scaledW) / 2.0 + shiftX
            let posY = (Double(canvasH) - scaledH) / 2.0 + shiftY
            destRect = CGRect(x: posX, y: posY, width: scaledW, height: scaledH)

        case .fit:
            let baseScale = min(Double(canvasW) / Double(imgW), Double(canvasH) / Double(imgH))
            let scaledW = Double(imgW) * baseScale * scaleXFactor
            let scaledH = Double(imgH) * baseScale * scaleYFactor
            let shiftX = (config.offsetX / 100.0) * Double(canvasW)
            let shiftY = (config.offsetY / 100.0) * Double(canvasH)
            let posX = (Double(canvasW) - scaledW) / 2.0 + shiftX
            let posY = (Double(canvasH) - scaledH) / 2.0 + shiftY
            destRect = CGRect(x: posX, y: posY, width: scaledW, height: scaledH)

        case .fill:
            let overspray = config.borderless ? (config.bleedPct / 100.0) : 0.0
            let targetW = Double(canvasW) * (1.0 + overspray)
            let targetH = Double(canvasH) * (1.0 + overspray)
            let baseScale = max(targetW / Double(imgW), targetH / Double(imgH))
            let scaledW = Double(imgW) * baseScale * scaleXFactor
            let scaledH = Double(imgH) * baseScale * scaleYFactor
            let shiftX = (config.offsetX / 100.0) * Double(canvasW)
            let shiftY = (config.offsetY / 100.0) * Double(canvasH)
            let posX = (Double(canvasW) - scaledW) / 2.0 + shiftX
            let posY = (Double(canvasH) - scaledH) / 2.0 + shiftY
            destRect = CGRect(x: posX, y: posY, width: scaledW, height: scaledH)

        case .compensate:
            // Fullbleed hardware compensation: 100% width coverage + safe bottom feed margin
            let shrinkH = min(0.20, max(0.0, config.compY / 100.0))
            let safeH = max(100.0, Double(canvasH) * (1.0 - shrinkH))

            let baseScale = max(Double(canvasW) / Double(imgW), safeH / Double(imgH))
            let scaledW = Double(imgW) * baseScale * scaleXFactor
            let scaledH = Double(imgH) * baseScale * scaleYFactor

            let shiftX = (config.offsetX / 100.0) * Double(canvasW)
            let shiftY = (config.offsetY / 100.0) * Double(canvasH)

            let posX = (Double(canvasW) - scaledW) / 2.0 + shiftX
            let posY = (safeH - scaledH) + shiftY
            destRect = CGRect(x: posX, y: posY, width: scaledW, height: scaledH)
        }

        // Render to 16-bit RGBA bitmap context
        let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
        let bytesPerPixel = 8 // 4 channels * 2 bytes = 8
        let bytesPerRow = canvasW * bytesPerPixel
        var buffer = Data(count: canvasH * bytesPerRow)

        let success = buffer.withUnsafeMutableBytes { rawBytes -> Bool in
            guard let baseAddr = rawBytes.baseAddress else { return false }
            guard let ctx = CGContext(
                data: baseAddr,
                width: canvasW,
                height: canvasH,
                bitsPerComponent: 16,
                bytesPerRow: bytesPerRow,
                space: colorSpace,
                bitmapInfo: CGBitmapInfo.byteOrder16Little.rawValue | CGImageAlphaInfo.premultipliedLast.rawValue
            ) else {
                return false
            }

            // Fill canvas with solid white (65535)
            ctx.setFillColor(red: 1.0, green: 1.0, blue: 1.0, alpha: 1.0)
            ctx.fill(canvasRect)

            ctx.interpolationQuality = .high
            ctx.draw(srcImg, in: destRect)

            // For compensate mode: replicate the bottom safe row across the overspray margin
            if config.fitMode == .compensate {
                let shrinkH = min(0.20, max(0.0, config.compY / 100.0))
                let safeH = Int(round(Double(canvasH) * (1.0 - shrinkH)))
                if safeH > 0 && safeH < canvasH {
                    let ptr16 = baseAddr.assumingMemoryBound(to: UInt16.self)
                    let safeRowOffset = (safeH - 1) * canvasW * 4
                    for row in safeH..<canvasH {
                        let targetRowOffset = row * canvasW * 4
                        memcpy(ptr16 + targetRowOffset, ptr16 + safeRowOffset, canvasW * 4 * MemoryLayout<UInt16>.size)
                    }
                }
            }
            return true
        }

        guard success else {
            throw G640Error.imageRenderFailed
        }

        return (buffer, canvasW, canvasH)
    }

    /// Rotates a CGImage 90 degrees clockwise.
    private func rotateImage90CW(_ image: CGImage) -> CGImage? {
        let w = image.height
        let h = image.width
        let colorSpace = image.colorSpace ?? CGColorSpaceCreateDeviceRGB()

        guard let ctx = CGContext(
            data: nil,
            width: w,
            height: h,
            bitsPerComponent: image.bitsPerComponent,
            bytesPerRow: 0,
            space: colorSpace,
            bitmapInfo: image.bitmapInfo.rawValue
        ) else {
            return nil
        }

        ctx.translateBy(x: CGFloat(w), y: 0)
        ctx.rotate(by: .pi / 2.0)
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        return ctx.makeImage()
    }
}
