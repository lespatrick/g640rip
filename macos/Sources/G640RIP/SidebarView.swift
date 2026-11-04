import SwiftUI
import UniformTypeIdentifiers
import G640Core

struct SidebarView: View {
    @Bindable var state: G640AppState
    @State private var isCalibrationExpanded: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    printerSection
                    Divider()
                    paperSection
                    Divider()
                    profileSection
                    Divider()
                    framingSection
                    Divider()
                    softProofControls
                    Divider()
                    calibrationSection
                }
                .padding(16)
            }

            Divider()

            printActionSection
                .padding(16)
                .background(Color(nsColor: .windowBackgroundColor))
        }
        .frame(minWidth: 320, idealWidth: 340, maxWidth: 380)
        .background(Color(nsColor: .controlBackgroundColor))
    }

    // MARK: - Sections

    private var printerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Drukarka & Bufor", systemImage: "printer.fill")
                .font(.headline)

            HStack {
                Picker("Kolejka:", selection: $state.selectedQueue) {
                    ForEach(state.availableQueues) { q in
                        Text(q.name).tag(Optional(q))
                    }
                }
                .labelsHidden()

                Button {
                    state.refreshPrinters()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Odśwież kolejki systemowe CUPS")
            }

            if let q = state.selectedQueue {
                Text(q.statusDescription)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            Button(role: .destructive) {
                state.cancelActiveJobs()
            } label: {
                Label("Anuluj aktywne zadania", systemImage: "xmark.circle")
                    .font(.caption)
            }
            .buttonStyle(.borderless)
        }
    }

    private var paperSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Format Papieru", systemImage: "doc.fill")
                .font(.headline)

            Picker("Rozmiar:", selection: $state.selectedPaper) {
                ForEach(state.availablePapers, id: \.self) { p in
                    Text(p.displayName).tag(p)
                }
            }
            .pickerStyle(.menu)

            Toggle("Druk bez marginesów (Fullbleed)", isOn: $state.geometryConfig.borderless)
                .font(.subheadline)
        }
    }

    private var profileSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Profil ICC Papieru", systemImage: "swatchpalette.fill")
                    .font(.headline)
                Spacer()
                Button {
                    state.scanProfiles()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Odśwież listę profili")
            }

            Picker("Profil:", selection: $state.selectedProfileURL) {
                Text("-- Brak (Standardowy sRGB) --").tag(nil as URL?)
                ForEach(state.availableProfiles, id: \.self) { url in
                    Text(url.lastPathComponent).tag(Optional(url))
                }
            }
            .pickerStyle(.menu)
            .onChange(of: state.selectedProfileURL) { _, _ in
                state.updateSoftProof()
            }

            Button("Wybierz inny plik ICC...") {
                openProfileDialog()
            }
            .font(.caption)
        }
    }

    private var framingSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Kadrowanie & Dopasowanie", systemImage: "crop")
                .font(.headline)

            Picker("Tryb:", selection: $state.geometryConfig.fitMode) {
                ForEach(FitMode.allCases) { m in
                    Text(m.displayName).tag(m)
                }
            }
            .pickerStyle(.menu)
            .onChange(of: state.geometryConfig.fitMode) { _, _ in
                state.updateSoftProof()
            }

            if state.geometryConfig.fitMode == .compensate {
                Text("Gwarantuje 100% szerokości papieru (zero powielonych pasków) i zabezpiecza dolną krawędź przed ucięciem przez rolki.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var softProofControls: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Soft Proofing (LittleCMS2)", systemImage: "eye.fill")
                .font(.headline)

            Toggle("Symuluj biel papieru (Absolute Colorimetric)", isOn: $state.simulatePaperWhite)
                .font(.subheadline)
                .onChange(of: state.simulatePaperWhite) { _, _ in
                    state.updateSoftProof()
                }

            Toggle("Ostrzeżenie o utracie gamutu (Alarm)", isOn: $state.showGamutWarning)
                .font(.subheadline)
                .onChange(of: state.showGamutWarning) { _, _ in
                    state.updateSoftProof()
                }

            Toggle("Podgląd dzielony (Split View)", isOn: $state.showProofSplit)
                .font(.subheadline)
        }
    }

    private var calibrationSection: some View {
        DisclosureGroup(isExpanded: $isCalibrationExpanded) {
            VStack(alignment: .leading, spacing: 10) {
                Text("Parametry skorygowane dla optyki i mechanizmu G640:")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                sliderRow(label: "Skala szerokości (X)", value: $state.geometryConfig.scaleX, range: -3.0...3.0, step: 0.1, unit: "%")
                sliderRow(label: "Skala długości (Y)", value: $state.geometryConfig.scaleY, range: -3.0...3.0, step: 0.05, unit: "%")
                sliderRow(label: "Przesunięcie X", value: $state.geometryConfig.offsetX, range: -3.0...3.0, step: 0.05, unit: "%")
                sliderRow(label: "Przesunięcie Y", value: $state.geometryConfig.offsetY, range: -3.0...3.0, step: 0.05, unit: "%")
                sliderRow(label: "Margines rolek", value: $state.geometryConfig.compY, range: 0.0...10.0, step: 0.5, unit: "%")

                Button("Przywróć domyślne kalibrowane") {
                    state.geometryConfig = .calibratedDefault
                }
                .font(.caption)

                Divider()

                Button {
                    state.showCalibrationStudio = true
                } label: {
                    Label("Otwórz Studio Kalibracji...", systemImage: "slider.horizontal.2.square")
                        .font(.caption)
                }
            }
            .padding(.top, 6)
        } label: {
            Label("Kalibracja Sprzętowa", systemImage: "slider.horizontal.3")
                .font(.headline)
        }
    }

    private var printActionSection: some View {
        VStack(spacing: 12) {
            Button {
                Task {
                    await state.printActivePhoto()
                }
            } label: {
                HStack {
                    if state.isPrinting {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Image(systemName: "printer.fill")
                    }
                    Text("Drukuj (Bypass ColorSync)")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(state.loadedCGImage == nil || state.isPrinting || state.selectedQueue == nil)

            Text(state.statusMessage)
                .font(.caption2)
                .foregroundStyle(state.isPrinting ? .primary : .secondary)
                .multilineTextAlignment(.center)
        }
    }

    private func sliderRow(label: String, value: Binding<Double>, range: ClosedRange<Double>, step: Double, unit: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label)
                    .font(.caption)
                Spacer()
                Text(String(format: "%+.2f%@", value.wrappedValue, unit))
                    .font(.caption.monospacedDigit())
            }
            Slider(value: value, in: range, step: step)
        }
    }

    private func openProfileDialog() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "icc")!, UTType(filenameExtension: "icm")!]
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            if !state.availableProfiles.contains(url) {
                state.availableProfiles.append(url)
            }
            state.selectedProfileURL = url
            state.updateSoftProof()
        }
    }
}

