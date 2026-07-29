// swift-tools-version: 6.3

import PackageDescription

let package = Package(
    name: "laguna-quality-bridge",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(
            name: "laguna-quality-bridge",
            targets: ["LagunaQualityBridge"]
        )
    ],
    dependencies: [
        .package(
            name: "mlxfast-challenge-dev",
            path: "../../.."
        ),
        .package(
            name: "mlx-swift",
            path: "../../../Vendor/mlx-swift"
        ),
        .package(
            name: "mlx-swift-lm",
            path: "../../../Vendor/mlx-swift-lm"
        ),
    ],
    targets: [
        .target(
            name: "LagunaQualityBridgeProtocol"
        ),
        .target(
            name: "LagunaQualityMetalShim",
            dependencies: [
                .product(name: "Cmlx", package: "mlx-swift")
            ],
            publicHeadersPath: "include"
        ),
        .executableTarget(
            name: "LagunaQualityBridge",
            dependencies: [
                "LagunaQualityBridgeProtocol",
                "LagunaQualityMetalShim",
                .product(
                    name: "MLXFastModel",
                    package: "mlxfast-challenge-dev"
                ),
                .product(name: "MLX", package: "mlx-swift"),
                .product(name: "MLXLMCommon", package: "mlx-swift-lm"),
            ]
        ),
        .testTarget(
            name: "LagunaQualityBridgeProtocolTests",
            dependencies: ["LagunaQualityBridgeProtocol"]
        ),
    ]
)
