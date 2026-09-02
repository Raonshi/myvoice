import Foundation

enum BackendError: LocalizedError {
    case unavailable(String)
    case failed(String)
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .unavailable(let detail): "MyVoice 백엔드를 찾을 수 없습니다. \(detail)"
        case .failed(let detail): detail
        case .invalidResponse: "백엔드가 올바르지 않은 응답을 반환했습니다."
        }
    }
}

struct BackendRun<Value: Sendable>: Sendable {
    let value: Value
    let progress: [String]
}

struct BackendClient: Sendable {
    func perform<T: Decodable & Sendable>(
        _ request: DesktopRequest,
        as type: T.Type
    ) async throws -> BackendRun<T> {
        try await Task.detached(priority: .userInitiated) {
            let encoder = JSONEncoder()
            let requestURL = FileManager.default.temporaryDirectory
                .appendingPathComponent("myvoice-\(UUID().uuidString).json")
            let stdoutURL = FileManager.default.temporaryDirectory
                .appendingPathComponent("myvoice-\(UUID().uuidString).stdout")
            let stderrURL = FileManager.default.temporaryDirectory
                .appendingPathComponent("myvoice-\(UUID().uuidString).stderr")
            try encoder.encode(request).write(to: requestURL, options: .atomic)
            _ = FileManager.default.createFile(atPath: stdoutURL.path, contents: nil)
            _ = FileManager.default.createFile(atPath: stderrURL.path, contents: nil)
            defer {
                try? FileManager.default.removeItem(at: requestURL)
                try? FileManager.default.removeItem(at: stdoutURL)
                try? FileManager.default.removeItem(at: stderrURL)
            }

            let invocation = try Self.resolveInvocation()
            let process = Process()
            process.executableURL = invocation.executable
            process.arguments = invocation.arguments + ["desktop-api", requestURL.path]
            process.currentDirectoryURL = invocation.workingDirectory
            let output = try FileHandle(forWritingTo: stdoutURL)
            let errors = try FileHandle(forWritingTo: stderrURL)
            process.standardOutput = output
            process.standardError = errors
            do { try process.run() }
            catch { throw BackendError.unavailable(error.localizedDescription) }
            process.waitUntilExit()
            try output.close()
            try errors.close()

            let stdout = try Data(contentsOf: stdoutURL)
            let stderr = try Data(contentsOf: stderrURL)
            let lines = String(decoding: stdout, as: UTF8.self).split(separator: "\n")
            let decoder = JSONDecoder()
            var result: BackendEnvelope?
            var progress: [String] = []
            for line in lines {
                guard let data = line.data(using: .utf8),
                      let envelope = try? decoder.decode(BackendEnvelope.self, from: data) else { continue }
                if envelope.type == "progress" { progress.append(Self.describe(envelope)) }
                if envelope.type == "result" { result = envelope }
            }
            guard let result else {
                let detail = String(decoding: stderr, as: UTF8.self)
                throw BackendError.failed(detail.isEmpty ? "백엔드 응답이 없습니다." : detail)
            }
            guard result.ok == true else { throw BackendError.failed(result.error ?? "작업에 실패했습니다.") }
            guard let value = result.data else { throw BackendError.invalidResponse }
            let data = try encoder.encode(value)
            return BackendRun(value: try decoder.decode(T.self, from: data), progress: progress)
        }.value
    }

    private static func resolveInvocation() throws -> (executable: URL, arguments: [String], workingDirectory: URL?) {
        let manager = FileManager.default
        let configured = UserDefaults.standard.string(forKey: "backendExecutable") ?? ""
        if !configured.isEmpty, manager.isExecutableFile(atPath: configured) {
            return (URL(fileURLWithPath: configured), [], URL(fileURLWithPath: configured).deletingLastPathComponent())
        }

        let repo = Bundle.main.bundleURL.deletingLastPathComponent().deletingLastPathComponent()
        let candidates = [
            repo.appendingPathComponent(".venv/bin/myvoice").path,
            "/opt/homebrew/bin/myvoice",
            "/usr/local/bin/myvoice",
        ]
        if let path = candidates.first(where: manager.isExecutableFile(atPath:)) {
            return (URL(fileURLWithPath: path), [], repo)
        }
        guard manager.isExecutableFile(atPath: "/usr/bin/env") else {
            throw BackendError.unavailable("Settings에서 myvoice 실행 파일을 지정하세요.")
        }
        return (URL(fileURLWithPath: "/usr/bin/env"), ["myvoice"], repo)
    }

    private static func describe(_ envelope: BackendEnvelope) -> String {
        switch envelope.event {
        case "enroll.reference": "Reference 음성을 전처리하고 품질을 분석했습니다."
        case "segment.started": "음성 세그먼트를 생성하고 있습니다."
        case "segment.completed": "세그먼트 생성이 완료되었습니다."
        case "job.assembled": "생성된 음성을 하나로 병합했습니다."
        case "job.completed": "AAC 파일 생성이 완료되었습니다."
        default: envelope.event ?? "작업을 처리했습니다."
        }
    }
}
