import XCTest
@testable import MyVoiceDesktop

final class BackendModelsTests: XCTestCase {
    func testSnapshotDecodesPythonSnakeCasePayload() throws {
        let json = #"{"version":"2.1.1","data_dir":"/tmp/myvoice","voices":[{"id":"v1","name":"voice","language":"ko","engine":"chatterbox_multilingual","engine_model":"v3","created_at":"now","references":["references/001.wav"],"primary_reference":"references/001.wav","sample_count":1,"total_duration_seconds":8.0,"consent_confirmed":true,"schema_version":1,"metadata":{}}],"jobs":[],"pronunciation_dictionaries":[{"id":"dictionary-1","name":"카메라","language":"ko","entries":[{"source":"Nikon","pronunciation":"니콘"}],"created_at":"now","updated_at":"now","schema_version":1}]}"#
        let snapshot = try JSONDecoder().decode(AppSnapshot.self, from: Data(json.utf8))
        XCTAssertEqual(snapshot.version, "2.1.1")
        XCTAssertEqual(snapshot.voices.first?.primaryReference, "references/001.wav")
        XCTAssertEqual(snapshot.pronunciationDictionaries.first?.entries.first?.source, "Nikon")
    }

    func testDesktopRequestEncodesBooleanAndNumberTypes() throws {
        let request = DesktopRequest(operation: "speak", payload: ["dry_run": .bool(false), "max_chars": .number(180)])
        let object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        let payload = object?["payload"] as? [String: Any]
        XCTAssertEqual(payload?["dry_run"] as? Bool, false)
        XCTAssertEqual(payload?["max_chars"] as? Double, 180)
    }

    func testDesktopRequestEncodesSampleFilesAndPronunciationEntries() throws {
        let request = DesktopRequest(operation: "enroll", payload: [
            "sample_files": .array([.string("/tmp/voice.aac"), .string("/tmp/voice.mp3")]),
            "entries": .array([
                .object(["source": .string("Nikon"), "pronunciation": .string("니콘")]),
            ]),
        ])
        let object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        let payload = object?["payload"] as? [String: Any]
        XCTAssertEqual(payload?["sample_files"] as? [String], ["/tmp/voice.aac", "/tmp/voice.mp3"])
        let entries = payload?["entries"] as? [[String: String]]
        XCTAssertEqual(entries?.first?["pronunciation"], "니콘")
    }
}
