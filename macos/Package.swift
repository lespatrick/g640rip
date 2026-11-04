// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "G640RIP",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(name: "G640Core", targets: ["G640Core"]),
        .executable(name: "G640RIP", targets: ["G640RIP"])
    ],
    targets: [
        .systemLibrary(
            name: "CLcms2",
            pkgConfig: "lcms2",
            providers: [
                .brew(["little-cms2"])
            ]
        ),
        .target(
            name: "G640Core",
            dependencies: ["CLcms2"]
        ),
        .executableTarget(
            name: "G640RIP",
            dependencies: ["G640Core"]
        ),
        .testTarget(
            name: "G640CoreTests",
            dependencies: ["G640Core"]
        )
    ]
)
