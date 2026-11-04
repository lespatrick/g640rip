import SwiftUI
import G640Core

struct ContentView: View {
    @State private var state = G640AppState()

    var body: some View {
        NavigationSplitView {
            SidebarView(state: state)
        } detail: {
            CanvasView(state: state)
        }
        .navigationTitle("Canon G640 Micro-RIP")
        .sheet(isPresented: $state.showCalibrationStudio) {
            CalibrationStudioSheet(state: state)
        }
        .toolbar {
            ToolbarItemGroup(placement: .automatic) {
                if state.loadedCGImage != nil {
                    Toggle(isOn: $state.showProofSplit) {
                        Label("Split Soft Proof", systemImage: "rectangle.split.2x1")
                    }
                    .help("Porównanie dzielone przed / po profilu")

                    Toggle(isOn: $state.showGamutWarning) {
                        Label("Gamut Alarm", systemImage: "exclamationmark.triangle")
                    }
                    .help("Podświetl piksele poza gamutem")
                }

                Button {
                    state.showCalibrationStudio = true
                } label: {
                    Label("Kalibracja", systemImage: "slider.horizontal.2.square")
                }
                .help("Druk wzorców kalibracyjnych 1:1")
            }
        }
    }
}

