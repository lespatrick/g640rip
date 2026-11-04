import SwiftUI
import AppKit

@main
struct G640RIPApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 900, idealWidth: 1200, minHeight: 650, idealHeight: 800)
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified)
    }
}

