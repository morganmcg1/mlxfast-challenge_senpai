// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "QKABIBench",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(path: "../../Vendor/mlx-swift"),
    ],
    targets: [
        .executableTarget(
            name: "QKABIBench",
            dependencies: [
                .product(name: "MLX", package: "mlx-swift"),
                .product(name: "MLXRandom", package: "mlx-swift"),
            ]
        ),
    ]
)
