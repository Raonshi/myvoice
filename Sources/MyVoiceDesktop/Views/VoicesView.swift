import SwiftUI

struct VoicesView: View {
    @EnvironmentObject private var store: AppStore
    @State private var selectedID: String?
    @State private var pendingDelete: VoiceProfile?

    private var selected: VoiceProfile? { store.voices.first { $0.id == selectedID } }

    var body: some View {
        HSplitView {
            List(store.voices, selection: $selectedID) { voice in
                VStack(alignment: .leading, spacing: 3) {
                    Text(voice.name).font(.headline)
                    Text("\(voice.language) · \(voice.sampleCount)개 샘플").font(.caption).foregroundStyle(.secondary)
                }.tag(voice.id)
            }.frame(minWidth: 230, idealWidth: 270)

            Group {
                if let voice = selected {
                    Form {
                        Section("Profile") {
                            LabeledContent("이름", value: voice.name)
                            LabeledContent("언어", value: voice.language)
                            LabeledContent("엔진", value: voice.engine)
                            LabeledContent("모델", value: voice.engineModel)
                        }
                        Section("Reference") {
                            LabeledContent("Primary", value: voice.primaryReference)
                            LabeledContent("샘플", value: voice.sampleCount.formatted())
                            LabeledContent("전체 길이", value: String(format: "%.1f초", voice.totalDurationSeconds))
                            Text("등록 과정은 가장 긴 파일이 아니라, 전처리 후 길이·무음·레벨 품질을 종합해 Primary reference를 선택합니다.")
                                .font(.callout).foregroundStyle(.secondary)
                        }
                        Section {
                            Button("Voice Profile 삭제", role: .destructive) { pendingDelete = voice }
                                .disabled(store.isWorking)
                        }
                    }.formStyle(.grouped)
                } else {
                    ContentUnavailableView("Voice Profile을 선택하세요", systemImage: "person.wave.2")
                }
            }.frame(minWidth: 400)
        }
        .navigationTitle("Voice Profiles")
        .onAppear { selectedID = selectedID ?? store.voices.first?.id }
        .confirmationDialog("Voice Profile을 삭제할까요?", isPresented: Binding(
            get: { pendingDelete != nil }, set: { if !$0 { pendingDelete = nil } }
        )) {
            Button("삭제", role: .destructive) {
                if let voice = pendingDelete { Task { await store.delete(voice) } }
                pendingDelete = nil
            }
            Button("취소", role: .cancel) { pendingDelete = nil }
        } message: { Text("Reference 파일도 함께 삭제되며 되돌릴 수 없습니다.") }
    }
}
