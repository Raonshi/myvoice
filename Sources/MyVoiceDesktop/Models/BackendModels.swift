import Foundation

enum JSONValue: Codable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else if let value = try? container.decode(Double.self) { self = .number(value) }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode([String: JSONValue].self) { self = .object(value) }
        else { self = .array(try container.decode([JSONValue].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }
}

struct DesktopRequest: Codable, Sendable {
    let operation: String
    var payload: [String: JSONValue] = [:]
}

struct BackendEnvelope: Codable, Sendable {
    let type: String
    var ok: Bool?
    var error: String?
    var data: JSONValue?
    var event: String?
    var payload: JSONValue?
}

struct AppSnapshot: Codable, Sendable {
    let version: String
    let dataDir: String
    let voices: [VoiceProfile]
    let jobs: [GenerationJob]

    enum CodingKeys: String, CodingKey {
        case version, voices, jobs
        case dataDir = "data_dir"
    }
}

struct VoiceProfile: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let name: String
    let language: String
    let engine: String
    let engineModel: String
    let createdAt: String
    let references: [String]
    let primaryReference: String
    let sampleCount: Int
    let totalDurationSeconds: Double
    let metadata: JSONValue?

    enum CodingKeys: String, CodingKey {
        case id, name, language, engine, references, metadata
        case engineModel = "engine_model"
        case createdAt = "created_at"
        case primaryReference = "primary_reference"
        case sampleCount = "sample_count"
        case totalDurationSeconds = "total_duration_seconds"
    }

    static func == (lhs: VoiceProfile, rhs: VoiceProfile) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

struct SpeechSegment: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let order: Int
    let normalizedText: String
    let status: String
    let revision: Int
    let durationSeconds: Double?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case id, order, status, revision, error
        case normalizedText = "normalized_text"
        case durationSeconds = "duration_seconds"
    }
}

struct GenerationJob: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let status: String
    let createdAt: String
    let voiceName: String
    let device: String
    let outputPath: String
    let segments: [SpeechSegment]
    let error: String?

    enum CodingKeys: String, CodingKey {
        case id, status, device, segments, error
        case createdAt = "created_at"
        case voiceName = "voice_name"
        case outputPath = "output_path"
    }
}

struct DoctorSnapshot: Codable, Sendable {
    let version: String
    let autoDevice: String
    let checks: [DoctorCheck]

    enum CodingKeys: String, CodingKey {
        case version, checks
        case autoDevice = "auto_device"
    }
}

struct DoctorCheck: Codable, Identifiable, Sendable {
    var id: String { name }
    let name: String
    let status: String
    let detail: String
}

struct DeletedVoice: Codable, Sendable { let deleted: String }

enum SidebarItem: String, CaseIterable, Identifiable {
    case overview = "개요"
    case generate = "음성 생성"
    case enroll = "음성 등록"
    case voices = "Voice Profiles"
    case jobs = "생성 작업"
    case doctor = "시스템 진단"

    var id: String { rawValue }
    var symbol: String {
        switch self {
        case .overview: "square.grid.2x2"
        case .generate: "waveform"
        case .enroll: "mic.badge.plus"
        case .voices: "person.wave.2"
        case .jobs: "clock.arrow.circlepath"
        case .doctor: "stethoscope"
        }
    }
}
