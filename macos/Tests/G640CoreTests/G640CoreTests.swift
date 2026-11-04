import Testing
import Foundation
import CoreGraphics
@testable import G640Core

@Test func testProfileCreation() throws {
    let srgb = ICCProfile.sRGB()
    #expect(Int(bitPattern: srgb.handle) != 0)

    let nullProfile = ICCProfile.null()
    #expect(Int(bitPattern: nullProfile.handle) != 0)
}

@Test func testColorTransformIdentity() throws {
    let profile1 = ICCProfile.sRGB()
    let profile2 = ICCProfile.sRGB()

    let transform = try ColorTransform(
        input: profile1,
        inFormat: LCMS2PixelFormat.rgb8,
        output: profile2,
        outFormat: LCMS2PixelFormat.rgb8,
        intent: .relativeColorimetric
    )

    let inputPixel: [UInt8] = [128, 64, 200]
    var outputPixel: [UInt8] = [0, 0, 0]

    inputPixel.withUnsafeBytes { inBytes in
        outputPixel.withUnsafeMutableBytes { outBytes in
            transform.transform(
                input: inBytes.baseAddress!,
                output: outBytes.baseAddress!,
                pixelCount: 1
            )
        }
    }

    // In identity transform, pixel values should match within 1 unit
    #expect(abs(Int(outputPixel[0]) - 128) <= 1)
    #expect(abs(Int(outputPixel[1]) - 64) <= 1)
    #expect(abs(Int(outputPixel[2]) - 200) <= 1)
}

@Test func testAppleRasterEncoderHeader() throws {
    let w = 8
    let h = 4
    let pixelCount = w * h
    // White buffer: 8x4 * 3 = 96 bytes of 0xFF
    let buffer = Data(repeating: 255, count: pixelCount * 3)

    let urf = try AppleRasterEncoder.encodeRGB24(
        rgbBuffer: buffer,
        width: w,
        height: h,
        dpi: 600,
        quality: 5
    )

    #expect(urf.count >= 40) // 12 bytes file header + 28 bytes page header
    let magic = String(data: urf.prefix(7), encoding: .ascii)
    #expect(magic == "UNIRAST")
    #expect(urf[7] == 0x00) // null byte

    // Check page header width and height at bytes 24..31
    let wBigEndian = urf.subdata(in: 24..<28).withUnsafeBytes { $0.load(as: UInt32.self) }
    let hBigEndian = urf.subdata(in: 28..<32).withUnsafeBytes { $0.load(as: UInt32.self) }
    #expect(UInt32(bigEndian: wBigEndian) == UInt32(w))
    #expect(UInt32(bigEndian: hBigEndian) == UInt32(h))
}

@Test func testGeometryConfigDefaults() {
    let config = GeometryConfig.calibratedDefault
    #expect(config.scaleX == -1.0)
    #expect(config.scaleY == 0.59)
    #expect(config.offsetX == -0.25)
    #expect(config.offsetY == -1.59)
    #expect(config.compY == 5.0)
    #expect(config.fitMode == .compensate)
}

@Test func testDiscoverQueues() {
    let queues = CUPSRawSpooler.discoverQueues()
    // Should discover at least system default printer or Canon queue
    #expect(!queues.isEmpty)
    print("Discovered CUPS queues: \(queues.map(\.name))")
}

@Test func testSoftProofRendering() throws {
    let srgb = ICCProfile.sRGB()
    let paper = ICCProfile.sRGB()

    let cs = CGColorSpace(name: CGColorSpace.sRGB)!
    let ctx = CGContext(
        data: nil,
        width: 10,
        height: 10,
        bitsPerComponent: 8,
        bytesPerRow: 40,
        space: cs,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    )!
    ctx.setFillColor(red: 0.8, green: 0.4, blue: 0.2, alpha: 1.0)
    ctx.fill(CGRect(x: 0, y: 0, width: 10, height: 10))
    let img = ctx.makeImage()!

    let (proof, _) = try SoftProofEngine.renderSoftProof(
        image: img,
        paperProfile: paper,
        displayProfile: srgb,
        simulatePaperWhite: false,
        highlightGamutAlarm: false
    )

    let data = proof.dataProvider?.data as Data?
    #expect(data != nil)
    if let d = data {
        let bytes = [UInt8](d.prefix(8))
        print("First 8 bytes of proof image: \(bytes)")
        #expect(bytes[3] == 255) // Alpha channel should be 255!
    }
}
