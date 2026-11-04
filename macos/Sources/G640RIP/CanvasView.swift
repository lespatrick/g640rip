import SwiftUI
import CoreGraphics
import UniformTypeIdentifiers
import G640Core

struct HClipShape: Shape {
    var progress: Double

    var animatableData: Double {
        get { progress }
        set { progress = newValue }
    }

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.addRect(CGRect(x: 0, y: 0, width: rect.width * CGFloat(progress), height: rect.height))
        return path
    }
}

struct CanvasView: View {
    @Bindable var state: G640AppState

    var body: some View {
        ZStack {
            Color(white: 0.16)
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
                .foregroundStyle(.white)

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
                let origCg = state.loadedCGImage
                let proofCg = state.proofCGImage ?? origCg

                if let proofCg = proofCg, let origCg = origCg {
                    let origNs = NSImage(cgImage: origCg, size: NSSize(width: origCg.width, height: origCg.height))
                    let proofNs = NSImage(cgImage: proofCg, size: NSSize(width: proofCg.width, height: proofCg.height))

                    switch state.previewMode {
                    case .original:
                        Image(nsImage: origNs)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .padding(20)
                            .shadow(color: .black.opacity(0.4), radius: 12, x: 0, y: 6)

                    case .proof:
                        ZStack {
                            Image(nsImage: proofNs)
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .padding(20)
                                .shadow(color: .black.opacity(0.4), radius: 12, x: 0, y: 6)

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

                    case .split:
                        splitView(original: origNs, proofed: proofNs, containerSize: geo.size)
                    }
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
    }

    @ViewBuilder
    private func splitView(original: NSImage, proofed: NSImage, containerSize: CGSize) -> some View {
        let padding: CGFloat = 20
        let availableWidth = max(50, containerSize.width - padding * 2)
        let availableHeight = max(50, containerSize.height - padding * 2)

        // Compute fitted image display rect to position divider and mask correctly
        let imgW = original.size.width
        let imgH = original.size.height
        let scale = min(availableWidth / imgW, availableHeight / imgH)
        let fitW = imgW * scale
        let fitH = imgH * scale

        ZStack {
            // Container centered
            ZStack(alignment: .leading) {
                // Background: "PO" (Proofed)
                Image(nsImage: proofed)
                    .resizable()
                    .frame(width: fitW, height: fitH)

                // Foreground: "PRZED" (Original) clipped to splitPosition
                Image(nsImage: original)
                    .resizable()
                    .frame(width: fitW, height: fitH)
                    .clipShape(HClipShape(progress: state.splitPosition))

                // Divider line with circular handle
                Rectangle()
                    .fill(Color.white)
                    .frame(width: 2, height: fitH)
                    .overlay(
                        Circle()
                            .fill(Color.white)
                            .frame(width: 26, height: 26)
                            .shadow(radius: 4)
                            .overlay(
                                Image(systemName: "chevron.left.chevron.right")
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundStyle(.black)
                            )
                    )
                    .position(x: fitW * CGFloat(state.splitPosition), y: fitH / 2)
                    .gesture(
                        DragGesture()
                            .onChanged { val in
                                let pos = max(0.01, min(0.99, Double(val.location.x / fitW)))
                                state.splitPosition = pos
                            }
                    )

                // Badges
                HStack {
                    Text("PRZED (Oryginał)")
                        .font(.caption2.bold())
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(.black.opacity(0.7))
                        .foregroundStyle(.white)
                        .cornerRadius(4)
                        .padding(8)

                    Spacer()

                    Text("PO (Soft Proof)")
                        .font(.caption2.bold())
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(.black.opacity(0.7))
                        .foregroundStyle(.white)
                        .cornerRadius(4)
                        .padding(8)
                }
                .frame(width: fitW, height: fitH, alignment: .top)
            }
            .frame(width: fitW, height: fitH)
            .shadow(color: .black.opacity(0.5), radius: 14, x: 0, y: 6)
        }
        .frame(width: containerSize.width, height: containerSize.height)
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
