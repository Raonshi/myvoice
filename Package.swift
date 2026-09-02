// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "MyVoiceDesktop",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "MyVoiceDesktop", targets: ["MyVoiceDesktop"]),
    ],
    targets: [
        .executableTarget(
            name: "MyVoiceDesktop",
            path: "Sources/MyVoiceDesktop"
        ),
        .testTarget(
            name: "MyVoiceDesktopTests",
            dependencies: ["MyVoiceDesktop"],
            path: "Tests/MyVoiceDesktopTests"
        ),
    ]
)
