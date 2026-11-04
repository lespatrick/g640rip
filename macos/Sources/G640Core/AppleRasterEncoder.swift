import Foundation

public final class AppleRasterEncoder: Sendable {
    public init() {}

    /// Encodes a single row of RGB24 pixels using URF PackBits RLE compression.
    /// - Parameters:
    ///   - rowBytes: Pointer to 3 bytes per pixel [R, G, B, R, G, B, ...]
    ///   - width: Number of pixels in the row
    /// - Returns: PackBits encoded bytes
    public static func encodePackBitsRowRGB(
        rowBytes: UnsafePointer<UInt8>,
        width: Int
    ) -> Data {
        if width <= 0 { return Data() }

        // Find trailing white pixels (255, 255, 255) from right to left
        var trailingWhites = 0
        var ptr = rowBytes + (width - 1) * 3
        while trailingWhites < width {
            if ptr[0] == 255 && ptr[1] == 255 && ptr[2] == 255 {
                trailingWhites += 1
                ptr -= 3
            } else {
                break
            }
        }

        let activeWidth = (trailingWhites >= 4) ? (width - trailingWhites) : width
        let hasWhiteFill = activeWidth < width

        var out = Data()
        out.reserveCapacity(activeWidth * 3 + 16)
        var i = 0

        while i < activeWidth {
            // Count identical consecutive pixels (repeat run)
            var runLen = 1
            let curPtr = rowBytes + i * 3
            let r0 = curPtr[0], g0 = curPtr[1], b0 = curPtr[2]

            while (i + runLen < activeWidth) && (runLen < 128) {
                let nextPtr = rowBytes + (i + runLen) * 3
                if nextPtr[0] == r0 && nextPtr[1] == g0 && nextPtr[2] == b0 {
                    runLen += 1
                } else {
                    break
                }
            }

            if runLen >= 2 {
                // Repeat run: code = runLen - 1 (0x01..0x7F)
                let code = UInt8(runLen - 1)
                out.append(code)
                out.append(r0)
                out.append(g0)
                out.append(b0)
                i += runLen
            } else {
                // Literal run: collect non-repeating pixels
                let litStart = i
                i += 1
                while (i < activeWidth) && ((i - litStart) < 128) {
                    if (i + 1 < activeWidth) {
                        let p1 = rowBytes + i * 3
                        let p2 = rowBytes + (i + 1) * 3
                        if p1[0] == p2[0] && p1[1] == p2[1] && p1[2] == p2[2] {
                            break
                        }
                    }
                    i += 1
                }

                let litLen = i - litStart
                if litLen == 1 {
                    // Single pixel encoded as repeat 1 time (code = 0)
                    out.append(0)
                    let p = rowBytes + litStart * 3
                    out.append(p[0])
                    out.append(p[1])
                    out.append(p[2])
                } else {
                    // Literal run: code = (256 - litLen + 1) & 0xFF
                    let code = UInt8((256 - litLen + 1) & 0xFF)
                    out.append(code)
                    let startPtr = rowBytes + litStart * 3
                    out.append(startPtr, count: litLen * 3)
                }
            }
        }

        if hasWhiteFill {
            out.append(0x80)
        }

        return out
    }

    /// Encodes an RGB24 bitmap buffer into Apple Raster (image/urf v1.4).
    /// - Parameters:
    ///   - rgbBuffer: Contiguous buffer of width * height * 3 bytes
    ///   - width: Image width in pixels
    ///   - height: Image height in pixels
    ///   - dpi: Print resolution (default: 600 DPI for Canon G640)
    ///   - quality: Print quality (3=Draft, 4=Normal, 5=High)
    /// - Returns: Complete binary URF stream ready for direct socket transmission
    public static func encodeRGB24(
        rgbBuffer: Data,
        width: Int,
        height: Int,
        dpi: Int = 600,
        quality: UInt8 = 5
    ) throws -> Data {
        guard width > 0 && height > 0 else {
            throw G640Error.invalidDimensions(width, height)
        }
        guard rgbBuffer.count >= width * height * 3 else {
            throw G640Error.rasterEncodingFailed("Buffer size mismatch: expected \(width * height * 3), got \(rgbBuffer.count)")
        }

        var out = Data()
        out.reserveCapacity(min(rgbBuffer.count / 2, 50 * 1024 * 1024))

        // 1. File Header: "UNIRAST\0" (8 bytes) + page_count = 1 (uint32 big-endian)
        let magic: [UInt8] = [0x55, 0x4E, 0x49, 0x52, 0x41, 0x53, 0x54, 0x00] // "UNIRAST\0"
        out.append(contentsOf: magic)
        var pageCountBE = UInt32(1).bigEndian
        out.append(Data(bytes: &pageCountBE, count: 4))

        // 2. Page Header: 28 bytes
        // uint8_t bpp (24 for RGB)
        // uint8_t colorspace (1 for sRGB)
        // uint8_t duplex (0)
        // uint8_t quality (3-5)
        // uint32_t unknown0 (0)
        // uint32_t unknown1 (0)
        // uint32_t width
        // uint32_t height
        // uint32_t dpi
        // uint32_t unknown2 (0)
        // uint32_t unknown3 (0)
        out.append(24) // bpp
        out.append(1)  // colorspace: 1 = sRGB/RGB24
        out.append(0)  // duplex: 0 = simplex
        out.append(quality) // quality

        var u0 = UInt32(0).bigEndian
        out.append(Data(bytes: &u0, count: 4))
        var u1 = UInt32(0).bigEndian
        out.append(Data(bytes: &u1, count: 4))

        var wBE = UInt32(width).bigEndian
        out.append(Data(bytes: &wBE, count: 4))
        var hBE = UInt32(height).bigEndian
        out.append(Data(bytes: &hBE, count: 4))
        var dpiBE = UInt32(dpi).bigEndian
        out.append(Data(bytes: &dpiBE, count: 4))

        var u2 = UInt32(0).bigEndian
        out.append(Data(bytes: &u2, count: 4))
        var u3 = UInt32(0).bigEndian
        out.append(Data(bytes: &u3, count: 4))

        // 3. Scanlines with line-repeat compression
        let rowStride = width * 3

        rgbBuffer.withUnsafeBytes { rawBuffer in
            guard let basePtr = rawBuffer.baseAddress?.assumingMemoryBound(to: UInt8.self) else { return }

            var y = 0
            while y < height {
                let curRowPtr = basePtr + (y * rowStride)

                // Calculate line repeat count for identical consecutive rows
                var repeatCount: UInt8 = 0
                while (y + 1 + Int(repeatCount) < height) && (repeatCount < 254) {
                    let nextRowPtr = basePtr + ((y + 1 + Int(repeatCount)) * rowStride)
                    if memcmp(curRowPtr, nextRowPtr, rowStride) == 0 {
                        repeatCount += 1
                    } else {
                        break
                    }
                }

                // Line repeat byte
                out.append(repeatCount)

                // PackBits encode the row
                let rowData = encodePackBitsRowRGB(rowBytes: curRowPtr, width: width)
                out.append(rowData)

                y += 1 + Int(repeatCount)
            }
        }

        return out
    }
}
