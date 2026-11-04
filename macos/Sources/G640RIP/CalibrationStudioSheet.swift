import SwiftUI
import UniformTypeIdentifiers
import G640Core

struct CalibrationStudioSheet: View {
    @Bindable var state: G640AppState
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 20) {
            HStack {
                Label("Studio Kalibracji & Weryfikacji G640", systemImage: "slider.horizontal.2.square")
                    .font(.title2.bold())
                Spacer()
                Button("Zamknij") {
                    dismiss()
                }
            }

            Text("Drukuj wzorce pomiarowe w trybie 1:1 bit-exact, bez żadnego zarządzania barwą ani ingerencji ColorSync.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)

            Divider()

            VStack(alignment: .leading, spacing: 16) {
                Text("Dostępne Wzorce Kalibracyjne:")
                    .font(.headline)

                targetCard(
                    title: "Wzorzec Argyll 80 pól (4x6\" / 10x15 cm)",
                    subtitle: "Szybki wzorzec jednookładkowy do profilowania papieru (G640_10x15_80p_i1.tif)",
                    fileName: "G640_10x15_80p_i1.tif"
                )

                targetCard(
                    title: "Pasek Kontrolny QA (4x6\" / 600 DPI)",
                    subtitle: "ColorChecker 24, szara rampa 21 kroków, pamięciowe kolory nieba i skóry",
                    fileName: "QA_Control_Strip_4x6.png"
                )
            }

            Spacer()
        }
        .padding(24)
        .frame(minWidth: 540, minHeight: 400)
    }

    private func targetCard(title: String, subtitle: String, fileName: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.headline)
            Text(subtitle)
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack {
                Button {
                    let cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                    let targetURL = cwd.appendingPathComponent("targets").appendingPathComponent(fileName)
                    Task {
                        await state.printCalibrationTarget(targetURL: targetURL)
                    }
                } label: {
                    Label("Drukuj 1:1 bez profilu", systemImage: "printer.fill")
                }
                .disabled(state.isPrinting || state.selectedQueue == nil)

                Spacer()
            }
            .padding(.top, 4)
        }
        .padding(14)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(8)
    }
}
