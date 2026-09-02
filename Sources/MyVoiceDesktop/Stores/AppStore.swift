import Foundation
import SwiftUI

@MainActor
final class AppStore: ObservableObject {
    @Published var selection: SidebarItem? = .overview
    @Published var voices: [VoiceProfile] = []
    @Published var jobs: [GenerationJob] = []
    @Published var pronunciationDictionaries: [PronunciationDictionaryRecord] = []
    @Published var importedPronunciationDictionary: PronunciationDictionaryRecord?
    @Published var doctor: DoctorSnapshot?
    @Published var version = "2.1.0"
    @Published var dataDirectory = ""
    @Published var isWorking = false
    @Published var activity = "준비됨"
    @Published var lastError: String?

    private let backend = BackendClient()

    func refresh() async {
        await run("데이터를 새로 고치는 중") {
            let response = try await backend.perform(DesktopRequest(operation: "snapshot"), as: AppSnapshot.self)
            voices = response.value.voices
            jobs = response.value.jobs
            pronunciationDictionaries = response.value.pronunciationDictionaries
            version = response.value.version
            dataDirectory = response.value.dataDir
        }
    }

    func diagnose() async {
        await run("시스템을 진단하는 중") {
            doctor = try await backend.perform(DesktopRequest(operation: "doctor"), as: DoctorSnapshot.self).value
        }
    }

    func enroll(files: [String], name: String, language: String, replace: Bool) async {
        await run("Reference 음질을 분석하는 중") {
            _ = try await backend.perform(DesktopRequest(operation: "enroll", payload: [
                "sample_files": .array(files.map(JSONValue.string)), "name": .string(name),
                "language": .string(language), "consent_confirmed": .bool(true),
                "replace": .bool(replace),
            ]), as: VoiceProfile.self)
            selection = .voices
            try await reloadSnapshot()
        }
    }

    func speak(
        script: String,
        voice: String,
        output: String,
        device: String,
        dictionary: String,
        dictionaryID: String,
        maxChars: Int,
        keepMaster: Bool,
        dryRun: Bool
    ) async {
        await run(dryRun ? "대본을 분석하는 중" : "음성을 생성하는 중") {
            var payload: [String: JSONValue] = [
                "script": .string(script), "voice": .string(voice), "output": .string(output),
                "device": .string(device), "max_chars": .number(Double(maxChars)),
                "keep_master_wav": .bool(keepMaster), "dry_run": .bool(dryRun),
            ]
            if !dictionary.isEmpty { payload["pronunciation_dict"] = .string(dictionary) }
            if !dictionaryID.isEmpty { payload["pronunciation_dictionary_id"] = .string(dictionaryID) }
            _ = try await backend.perform(DesktopRequest(operation: "speak", payload: payload), as: GenerationJob.self)
            selection = .jobs
            try await reloadSnapshot()
        }
    }

    func resume(_ job: GenerationJob) async {
        await jobOperation("작업을 재개하는 중", operation: "resume", payload: ["job_id": .string(job.id)])
    }

    func regenerate(job: GenerationJob, segment: SpeechSegment, text: String) async {
        await jobOperation("세그먼트를 다시 생성하는 중", operation: "regenerate", payload: [
            "job_id": .string(job.id), "segment_id": .string(segment.id), "text": .string(text),
        ])
    }

    func delete(_ voice: VoiceProfile) async {
        await run("Voice Profile을 삭제하는 중") {
            _ = try await backend.perform(DesktopRequest(operation: "delete_voice", payload: ["name": .string(voice.name)]), as: DeletedVoice.self)
            try await reloadSnapshot()
        }
    }

    func savePronunciationDictionary(
        id: String?,
        name: String,
        language: String,
        entries: [PronunciationEntry]
    ) async {
        await run("발음 사전을 저장하는 중") {
            var payload: [String: JSONValue] = [
                "name": .string(name),
                "language": .string(language),
                "entries": .array(entries.map {
                    .object([
                        "source": .string($0.source),
                        "pronunciation": .string($0.pronunciation),
                    ])
                }),
            ]
            if let id { payload["id"] = .string(id) }
            _ = try await backend.perform(
                DesktopRequest(operation: "save_pronunciation_dictionary", payload: payload),
                as: PronunciationDictionaryRecord.self
            )
            try await reloadSnapshot()
        }
    }

    func delete(_ dictionary: PronunciationDictionaryRecord) async {
        await run("발음 사전을 삭제하는 중") {
            _ = try await backend.perform(
                DesktopRequest(
                    operation: "delete_pronunciation_dictionary",
                    payload: ["id": .string(dictionary.id)]
                ),
                as: DeletedPronunciationDictionary.self
            )
            try await reloadSnapshot()
        }
    }

    func loadPronunciationDictionary(path: String) async {
        importedPronunciationDictionary = nil
        await run("발음 사전을 불러오는 중") {
            importedPronunciationDictionary = try await backend.perform(
                DesktopRequest(
                    operation: "load_pronunciation_dictionary_file",
                    payload: ["path": .string(path)]
                ),
                as: PronunciationDictionaryRecord.self
            ).value
        }
    }

    private func jobOperation(_ label: String, operation: String, payload: [String: JSONValue]) async {
        await run(label) {
            _ = try await backend.perform(DesktopRequest(operation: operation, payload: payload), as: GenerationJob.self)
            try await reloadSnapshot()
        }
    }

    private func reloadSnapshot() async throws {
        let response = try await backend.perform(DesktopRequest(operation: "snapshot"), as: AppSnapshot.self)
        voices = response.value.voices
        jobs = response.value.jobs
        pronunciationDictionaries = response.value.pronunciationDictionaries
        version = response.value.version
        dataDirectory = response.value.dataDir
    }

    private func run(_ label: String, operation: () async throws -> Void) async {
        guard !isWorking else { return }
        isWorking = true
        lastError = nil
        activity = label
        do {
            try await operation()
            activity = "완료"
        } catch {
            lastError = error.localizedDescription
            activity = "실패"
        }
        isWorking = false
    }
}
