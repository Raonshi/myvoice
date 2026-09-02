import SwiftUI

struct EnrollView: View {
    @EnvironmentObject private var store: AppStore
    @State private var directory = ""
    @State private var name = ""
    @State private var language = "ko"
    @State private var hasRights = false
    @State private var replace = false

    var body: some View {
        Form {
            Section("Voice Profile") {
                LabeledContent("샘플 폴더") {
                    HStack {
                        Text(directory.isEmpty ? "선택되지 않음" : directory).lineLimit(1).foregroundStyle(.secondary)
                        Button("선택…") { directory = FilePanels.chooseDirectory() ?? directory }
                    }
                }
                TextField("이름", text: $name, prompt: Text("예: narration-ko"))
                Picker("언어", selection: $language) {
                    Text("한국어").tag("ko")
                    Text("English").tag("en")
                    Text("日本語").tag("ja")
                    Text("中文").tag("zh")
                }.frame(maxWidth: 280)
            }
            Section("자연스러운 결과를 위한 권장 녹음") {
                Label("한 화자가 자연스럽게 말한 선명한 6~10초 구간", systemImage: "waveform.badge.mic")
                Label("배경 음악·다른 화자·긴 무음·강한 잔향이 없는 원본", systemImage: "speaker.slash")
                Label("여러 파일 중 전처리 후 신호 품질이 가장 높은 음성을 자동 선택", systemImage: "wand.and.stars")
                Text("MyVoice는 앞뒤 무음을 제거하고 음량을 안정화하지만, 강한 노이즈 제거나 음색을 바꾸는 처리는 하지 않습니다.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Section {
                Toggle("본인의 음성이거나 명시적인 사용 권한이 있습니다", isOn: $hasRights)
                Toggle("같은 이름의 Profile이 있으면 교체", isOn: $replace)
            }
            Section {
                Button {
                    Task { await store.enroll(directory: directory, name: name, language: language, replace: replace) }
                } label: { Label("분석하고 등록", systemImage: "mic.badge.plus") }
                .buttonStyle(.borderedProminent)
                .disabled(directory.isEmpty || name.trimmingCharacters(in: .whitespaces).isEmpty || !hasRights || store.isWorking)
            }
        }.formStyle(.grouped).navigationTitle("음성 등록")
    }
}
