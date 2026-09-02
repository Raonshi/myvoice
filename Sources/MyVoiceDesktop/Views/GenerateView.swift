import SwiftUI

struct GenerateView: View {
    @EnvironmentObject private var store: AppStore
    @AppStorage("preferredDevice") private var device = "auto"
    @State private var script = ""
    @State private var output = ""
    @State private var dictionary = ""
    @State private var voice = ""
    @State private var maxChars = 180.0
    @State private var keepMaster = true
    @State private var dryRun = false

    var body: some View {
        Form {
            Section("입력") {
                fileRow("대본", value: script) { script = FilePanels.chooseFile(types: ["txt", "md", "markdown"]) ?? script }
                Picker("Voice Profile", selection: $voice) {
                    Text("선택하세요").tag("")
                    ForEach(store.voices) { Text($0.name).tag($0.name) }
                }
                fileRow("발음 사전 (선택)", value: dictionary) { dictionary = FilePanels.chooseFile(types: ["yaml", "yml"]) ?? dictionary }
            }
            Section("출력") {
                fileRow("AAC 파일", value: output) { output = FilePanels.saveAAC() ?? output }
                Picker("처리 장치", selection: $device) {
                    Text("자동 (Apple Silicon MPS 우선)").tag("auto")
                    Text("MPS").tag("mps")
                    Text("CPU").tag("cpu")
                }
                LabeledContent("세그먼트 최대 글자 수") {
                    HStack {
                        Slider(value: $maxChars, in: 20...400, step: 10).frame(width: 180)
                        Text(Int(maxChars).formatted()).monospacedDigit().frame(width: 36)
                    }
                }
                Toggle("Master WAV 보관", isOn: $keepMaster)
                Toggle("Dry run — 모델 실행 없이 세그먼트만 확인", isOn: $dryRun)
            }
            Section {
                Button {
                    Task {
                        await store.speak(script: script, voice: voice, output: output, device: device,
                                          dictionary: dictionary, maxChars: Int(maxChars),
                                          keepMaster: keepMaster, dryRun: dryRun)
                    }
                } label: { Label(dryRun ? "대본 분석" : "음성 생성", systemImage: dryRun ? "text.magnifyingglass" : "waveform") }
                .buttonStyle(.borderedProminent)
                .disabled(script.isEmpty || voice.isEmpty || output.isEmpty || store.isWorking)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("음성 생성")
        .onAppear { if voice.isEmpty { voice = store.voices.first?.name ?? "" } }
    }

    private func fileRow(_ label: String, value: String, choose: @escaping () -> Void) -> some View {
        LabeledContent(label) {
            HStack {
                Text(value.isEmpty ? "선택되지 않음" : value).lineLimit(1).foregroundStyle(.secondary)
                Button("선택…", action: choose)
            }
        }
    }
}
