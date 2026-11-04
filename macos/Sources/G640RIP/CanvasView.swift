import SwiftUI
import CoreGraphics
import UniformTypeIdentifiers
import G640Core

struct CanvasView: View {
    @Bindable var state: G640AppState

    var body: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor)
                .ignoresSafeArea()

            if let _ = state.loadedCGImage {
                imagePreview
            } else {
                dropPrompt
            }
        }
        .onDrop(of: [UTType.fileURL], isTargeted: nil) { providers in
            guard let provider = providers.first else { return false }
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                if let u = url {
                    Task { @MainActor in
                        state.loadImage(from: u)
                    }
                }
            }
            return true
        }
    }

    private var dropPrompt: some View {
        VStack(spacing: 16) {
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 64, weight: .light))
                .foregroundStyle(.secondary)

            Text("Przeciągnij i upuść fotografię tutaj")
                .font(.title2.weight(.medium))

            Text("Obsługiwane formaty: TIFF (16-bit), JPEG, PNG, HEIC, ProPhoto / AdobeRGB")
                .font(.caption)
                .foregroundStyle(.secondary)

            Button("Wybierz plik z dysku...") {
                openFileDialog()
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(40)
    }

    private var imagePreview: some View {
        GeometryReader { geo in
            ZStack {
                // Background neutral gray canvas for photography
                Color(white: 0.18)

                if let proofCg = state.proofCGImage {
                    let nsImg = NSImage(cgImage: proofCg, size: NSSize(width: proofCg.width, height: proofCg.height))

                    if state.showProofSplit, let origCg = state.loadedCGImage {
                        let origNs = NSImage(cgImage: origCg, size: NSSize(width: origCg.width, height: origCg.height))
                        splitView(original: origNs, proofed: nsImg, in: geo.size)
                    } else {
                        Image(nsImage: nsImg)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .padding(20)
                            .shadow(color: .black.opacity(0.4), radius: 12, x: 0, y: 6)
                    }

                    // Gamut alarm overlay
                    if state.showGamutWarning, let maskCg = state.gamutMaskCGImage {
                        let maskNs = NSImage(cgImage: maskCg, size: NSSize(width: maskCg.width, height: maskCg.height))
                        Image(nsImage: maskNs)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .padding(20)
                            .blendMode(.screen)
                            .allowsHitTesting(false)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func splitView(original: NSImage, proofed: NSImage, in size: CGSize) -> some View {
        ZStack {
            // Right / Proofed side
            Image(nsImage: proofed)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .padding(20)

            // Left / Original side (clipped by split position)
            Image(nsImage: original)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .padding(20)
                .mask(
                    GeometryReader { maskGeo in
                        Rectangle()
                            .frame(width: maskGeo.size.width * CGFloat(state.splitPosition))
                    }
                )

            // Divider line
            Rectangle()
                .fill(Color.white)
                .frame(width: 2)
                .position(x: size.width * CGFloat(state.splitPosition), y: size.height / 2)
                .shadow(radius: 4)
                .gesture(
                    DragGesture()
                        .onChanged { val in
                            let pos = max(0.05, min(0.95, Double(val.location.x / size.width)))
                            state.splitPosition = pos
                        }
                )
        }
    }

    private func openFileDialog() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.image, .tiff, .jpeg, .png]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            state.loadImage(from: url)
        }
    }
}
