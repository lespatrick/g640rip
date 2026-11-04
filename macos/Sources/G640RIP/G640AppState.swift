import Foundation
import CoreGraphics
import SwiftUI
import G640Core

@MainActor
@Observable
public final class G640AppState {
    public var selectedImageURL: URL? = nil
    public var loadedCGImage: CGImage? = nil
    public var loadedEmbeddedProfile: ICCProfile? = nil

    public var selectedPaper: PaperSpec = .photo4x6
    public var availablePapers: [PaperSpec] = PaperSpec.standardSizes

    public var selectedProfileURL: URL? = nil
    public var availableProfiles: [URL] = []

    public var geometryConfig: GeometryConfig = .calibratedDefault

    public var availableQueues: [PrinterQueue] = []
    public var selectedQueue: PrinterQueue? = nil

    // Soft proofing state
    public var simulatePaperWhite: Bool = false
    public var showGamutWarning: Bool = false
    public var splitPosition: Double = 0.5
    public var showProofSplit: Bool = false

    public var proofCGImage: CGImage? = nil
    public var gamutMaskCGImage: CGImage? = nil

    // UI & Execution state
    public var isProcessing: Bool = false
    public var isPrinting: Bool = false
    public var statusMessage: String = "Gotowy do pracy"
    public var lastPrintResult: PrintJobResult? = nil
    public var showCalibrationStudio: Bool = false

    public init() {
        refreshPrinters()
        scanProfiles()
    }

    public func refreshPrinters() {
        let queues = CUPSRawSpooler.discoverQueues()
        self.availableQueues = queues
        if self.selectedQueue == nil || !queues.contains(where: { $0.id == self.selectedQueue?.id }) {
            // Prefer Canon queue or default queue
            if let canon = queues.first(where: { $0.name.lowercased().contains("canon") || $0.name.lowercased().contains("g6") }) {
                self.selectedQueue = canon
            } else {
                self.selectedQueue = queues.first(where: { $0.isDefault }) ?? queues.first
            }
        }
    }

    public func scanProfiles() {
        var found: [URL] = []
        let fm = FileManager.default

        // 1. Project targets directory
        let cwd = URL(fileURLWithPath: fm.currentDirectoryPath)
        let targetsDir = cwd.appendingPathComponent("targets")
        if let items = try? fm.contentsOfDirectory(at: targetsDir, includingPropertiesForKeys: nil) {
            found.append(contentsOf: items.filter { $0.pathExtension.lowercased() == "icc" || $0.pathExtension.lowercased() == "icm" })
        }

        // 2. System and user ColorSync folders
        let homeDir = fm.homeDirectoryForCurrentUser
        let userColorSync = homeDir.appendingPathComponent("Library/ColorSync/Profiles")
        if let items = try? fm.contentsOfDirectory(at: userColorSync, includingPropertiesForKeys: nil) {
            found.append(contentsOf: items.filter { $0.pathExtension.lowercased() == "icc" || $0.pathExtension.lowercased() == "icm" })
        }

        self.availableProfiles = found.sorted(by: { $0.lastPathComponent < $1.lastPathComponent })
        if self.selectedProfileURL == nil, let first = found.first {
            self.selectedProfileURL = first
        }
    }

    public func loadImage(from url: URL) {
        do {
            let (cgImg, profile) = try ColorEngine.loadImage(from: url)
            self.selectedImageURL = url
            self.loadedCGImage = cgImg
            self.loadedEmbeddedProfile = profile
            self.statusMessage = "Wczytano obraz: \(url.lastPathComponent) (\(cgImg.width)x\(cgImg.height) px)"
            updateSoftProof()
        } catch {
            self.statusMessage = "Błąd wczytywania: \(error.localizedDescription)"
        }
    }

    public func updateSoftProof() {
        guard let src = loadedCGImage else {
            self.proofCGImage = nil
            self.gamutMaskCGImage = nil
            return
        }

        guard let profURL = selectedProfileURL,
              let paperProf = try? ICCProfile(path: profURL.path) else {
            self.proofCGImage = src
            self.gamutMaskCGImage = nil
            return
        }

        // Downscale preview if very large for instant 60 FPS slider responsiveness
        let maxPreviewDim = 1600
        let previewImg: CGImage
        if src.width > maxPreviewDim || src.height > maxPreviewDim {
            let scale = Double(maxPreviewDim) / Double(max(src.width, src.height))
            let pw = max(100, Int(Double(src.width) * scale))
            let ph = max(100, Int(Double(src.height) * scale))
            let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
            if let ctx = CGContext(
                data: nil,
                width: pw,
                height: ph,
                bitsPerComponent: 8,
                bytesPerRow: pw * 4,
                space: colorSpace,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) {
                ctx.interpolationQuality = .medium
                ctx.draw(src, in: CGRect(x: 0, y: 0, width: pw, height: ph))
                previewImg = ctx.makeImage() ?? src
            } else {
                previewImg = src
            }
        } else {
            previewImg = src
        }

        do {
            let (proof, mask) = try SoftProofEngine.renderSoftProof(
                image: previewImg,
                paperProfile: paperProf,
                simulatePaperWhite: simulatePaperWhite,
                highlightGamutAlarm: showGamutWarning
            )
            self.proofCGImage = proof
            self.gamutMaskCGImage = mask
        } catch {
            self.statusMessage = "Błąd soft proofingu: \(error.localizedDescription)"
        }
    }

    public func printActivePhoto() async {
        guard let src = loadedCGImage else {
            self.statusMessage = "Brak wczytanego zdjęcia!"
            return
        }
        guard let queue = selectedQueue else {
            self.statusMessage = "Brak wybranej drukarki!"
            return
        }

        self.isPrinting = true
        self.statusMessage = "Przetwarzanie 16-bit LittleCMS2 i kodowanie Apple Raster..."

        let config = self.geometryConfig
        let paper = self.selectedPaper
        let profURL = self.selectedProfileURL
        let inProf = self.loadedEmbeddedProfile
        let jobName = selectedImageURL?.lastPathComponent ?? "Photo Print"

        do {
            let paperProf = (profURL != nil) ? try ICCProfile(path: profURL!.path) : nil
            let engine = ColorEngine(paperProfile: paperProf)

            // Step 1: Render layout & transform in background
            let (rgbBuffer, finalW, finalH) = try await Task.detached(priority: .userInitiated) {
                try engine.processForPrint(
                    image: src,
                    inputProfile: inProf,
                    paper: paper,
                    config: config
                )
            }.value

            self.statusMessage = "Kodowanie bezstratnego Apple Raster (image/urf 600 DPI)..."

            // Step 2: Encode to URF
            let urfData = try await Task.detached(priority: .userInitiated) {
                try AppleRasterEncoder.encodeRGB24(
                    rgbBuffer: rgbBuffer,
                    width: finalW,
                    height: finalH,
                    dpi: 600,
                    quality: 5
                )
            }.value

            self.statusMessage = "Wysyłanie \(String(format: "%.1f", Double(urfData.count) / (1024 * 1024))) MB bezpośrednio do kolejki \(queue.name)..."

            // Step 3: Send via raw spooler
            let result = try CUPSRawSpooler.printRaw(
                urfData: urfData,
                queueName: queue.name,
                jobName: jobName,
                paper: paper,
                borderless: config.borderless
            )

            self.lastPrintResult = result
            self.statusMessage = "Wydruk wysłany pomyślnie! Zadanie: \(result.jobId ?? "OK") (ColorSync Bypassed)"
        } catch {
            self.statusMessage = "Błąd druku: \(error.localizedDescription)"
        }

        self.isPrinting = false
    }

    public func printCalibrationTarget(targetURL: URL) async {
        guard let queue = selectedQueue else {
            self.statusMessage = "Brak wybranej drukarki!"
            return
        }

        self.isPrinting = true
        self.statusMessage = "Druk targetu kalibracyjnego 1:1 (Zero Color Management)..."

        do {
            let (cgImg, _) = try ColorEngine.loadImage(from: targetURL)
            let canvasW = cgImg.width
            let canvasH = cgImg.height

            // Extract raw RGB8 directly with no color transforms
            let bytesPerRow = canvasW * 4
            var rawBuffer = Data(count: canvasH * bytesPerRow)
            let colorSpace = CGColorSpaceCreateDeviceRGB()

            let rendered = rawBuffer.withUnsafeMutableBytes { bytes -> Bool in
                guard let baseAddr = bytes.baseAddress else { return false }
                guard let ctx = CGContext(
                    data: baseAddr,
                    width: canvasW,
                    height: canvasH,
                    bitsPerComponent: 8,
                    bytesPerRow: bytesPerRow,
                    space: colorSpace,
                    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
                ) else { return false }
                ctx.interpolationQuality = .none
                ctx.draw(cgImg, in: CGRect(x: 0, y: 0, width: canvasW, height: canvasH))
                return true
            }

            guard rendered else {
                throw G640Error.imageRenderFailed
            }

            // Convert RGBA to RGB24
            var rgb24 = Data(count: canvasW * canvasH * 3)
            rawBuffer.withUnsafeBytes { inBytes in
                rgb24.withUnsafeMutableBytes { outBytes in
                    guard let pIn = inBytes.baseAddress?.assumingMemoryBound(to: UInt8.self),
                          let pOut = outBytes.baseAddress?.assumingMemoryBound(to: UInt8.self) else { return }
                    for i in 0..<(canvasW * canvasH) {
                        pOut[i * 3 + 0] = pIn[i * 4 + 0]
                        pOut[i * 3 + 1] = pIn[i * 4 + 1]
                        pOut[i * 3 + 2] = pIn[i * 4 + 2]
                    }
                }
            }

            let urfData = try AppleRasterEncoder.encodeRGB24(
                rgbBuffer: rgb24,
                width: canvasW,
                height: canvasH,
                dpi: 600,
                quality: 5
            )

            let result = try CUPSRawSpooler.printRaw(
                urfData: urfData,
                queueName: queue.name,
                jobName: targetURL.lastPathComponent,
                paper: selectedPaper,
                borderless: false
            )

            self.statusMessage = "Target wysłany 1:1! Zadanie: \(result.jobId ?? "OK")"
        } catch {
            self.statusMessage = "Błąd druku targetu: \(error.localizedDescription)"
        }

        self.isPrinting = false
    }

    public func cancelActiveJobs() {
        guard let q = selectedQueue else { return }
        CUPSRawSpooler.cancelJobs(queueName: q.name)
        self.statusMessage = "Wysłano polecenie anulowania zadań dla kolejki \(q.name)"
    }
}
