import SwiftUI

struct PronunciationDictionariesView: View {
    @EnvironmentObject private var store: AppStore
    @State private var selectedID: String?
    @State private var draftID: String?
    @State private var name = ""
    @State private var language = "ko"
    @State private var entries: [PronunciationEntry] = []
    @State private var localError: String?
    @State private var showDeleteConfirmation = false

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                List(selection: $selectedID) {
                    ForEach(store.pronunciationDictionaries) { dictionary in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(dictionary.name).lineLimit(1)
                            Text("\(dictionary.language) · \(dictionary.entries.count)개 항목")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .tag(dictionary.id)
                    }
                }
                .listStyle(.sidebar)

                HStack {
                    Button {
                        beginNewDictionary()
                    } label: {
                        Label("새 사전", systemImage: "plus")
                    }
                    Button {
                        importYAML()
                    } label: {
                        Label("YAML 가져오기", systemImage: "square.and.arrow.down")
                    }
                    Spacer()
                }
                .labelStyle(.iconOnly)
                .padding(8)
            }
            .frame(minWidth: 210, idealWidth: 240, maxWidth: 290)

            editor
                .frame(minWidth: 430, maxWidth: .infinity, maxHeight: .infinity)
        }
        .navigationTitle("발음 사전")
        .onChange(of: selectedID) { _, newValue in
            guard let newValue,
                  let dictionary = store.pronunciationDictionaries.first(where: { $0.id == newValue }) else {
                return
            }
            load(dictionary)
        }
        .task {
            if selectedID == nil, let first = store.pronunciationDictionaries.first {
                selectedID = first.id
                load(first)
            } else if entries.isEmpty {
                beginNewDictionary()
            }
        }
        .alert("입력 내용을 확인해 주세요", isPresented: Binding(
            get: { localError != nil },
            set: { if !$0 { localError = nil } }
        )) {
            Button("확인", role: .cancel) {}
        } message: {
            Text(localError ?? "알 수 없는 오류")
        }
        .confirmationDialog(
            "‘\(name)’ 발음 사전을 삭제할까요?",
            isPresented: $showDeleteConfirmation,
            titleVisibility: .visible
        ) {
            Button("삭제", role: .destructive) { deleteCurrentDictionary() }
            Button("취소", role: .cancel) {}
        } message: {
            Text("삭제한 사전은 복구할 수 없습니다.")
        }
    }

    private var editor: some View {
        Form {
            Section("사전 정보") {
                TextField("이름", text: $name, prompt: Text("예: 카메라 용어"))
                Picker("언어", selection: $language) {
                    Text("한국어").tag("ko")
                    Text("English").tag("en")
                    Text("日本語").tag("ja")
                    Text("中文").tag("zh")
                }
                .frame(maxWidth: 280)
            }

            Section("발음 항목") {
                if entries.isEmpty {
                    ContentUnavailableView(
                        "등록된 항목이 없습니다",
                        systemImage: "character.book.closed",
                        description: Text("원문과 실제로 읽을 발음을 추가하세요.")
                    )
                    .frame(maxWidth: .infinity, minHeight: 130)
                } else {
                    VStack(spacing: 8) {
                        HStack {
                            Text("원문").frame(maxWidth: .infinity, alignment: .leading)
                            Text("읽을 발음").frame(maxWidth: .infinity, alignment: .leading)
                            Color.clear.frame(width: 24, height: 1)
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)

                        ForEach($entries) { $entry in
                            HStack {
                                TextField("예: Nikon", text: $entry.source)
                                TextField("예: 니콘", text: $entry.pronunciation)
                                Button {
                                    entries.removeAll { $0.id == entry.id }
                                } label: {
                                    Image(systemName: "minus.circle.fill")
                                }
                                .buttonStyle(.plain)
                                .foregroundStyle(.secondary)
                                .help("항목 삭제")
                            }
                        }
                    }
                }

                Button {
                    entries.append(PronunciationEntry(source: "", pronunciation: ""))
                } label: {
                    Label("항목 추가", systemImage: "plus")
                }
            }

            Section {
                HStack {
                    Button("저장") { saveDictionary() }
                        .buttonStyle(.borderedProminent)
                        .disabled(store.isWorking)
                    Button("삭제", role: .destructive) {
                        showDeleteConfirmation = true
                    }
                    .disabled(draftID == nil || store.isWorking)
                    Spacer()
                    Text(draftID == nil ? "새 사전" : "저장된 사전 편집")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .formStyle(.grouped)
    }

    private func beginNewDictionary() {
        selectedID = nil
        draftID = nil
        name = ""
        language = "ko"
        entries = [PronunciationEntry(source: "", pronunciation: "")]
    }

    private func load(_ dictionary: PronunciationDictionaryRecord) {
        draftID = dictionary.id.isEmpty ? nil : dictionary.id
        name = dictionary.name
        language = dictionary.language
        entries = dictionary.entries
    }

    private func importYAML() {
        guard let path = FilePanels.chooseFile(types: ["yaml", "yml"]) else { return }
        Task {
            await store.loadPronunciationDictionary(path: path)
            guard store.lastError == nil, let imported = store.importedPronunciationDictionary else { return }
            selectedID = nil
            load(imported)
        }
    }

    private func saveDictionary() {
        let normalizedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedLanguage = language.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedEntries = entries.map {
            PronunciationEntry(
                source: $0.source.trimmingCharacters(in: .whitespacesAndNewlines),
                pronunciation: $0.pronunciation.trimmingCharacters(in: .whitespacesAndNewlines)
            )
        }
        guard !normalizedName.isEmpty else {
            localError = "사전 이름을 입력하세요."
            return
        }
        guard !normalizedLanguage.isEmpty else {
            localError = "언어를 선택하세요."
            return
        }
        guard !normalizedEntries.isEmpty,
              normalizedEntries.allSatisfy({ !$0.source.isEmpty && !$0.pronunciation.isEmpty }) else {
            localError = "모든 항목의 원문과 읽을 발음을 입력하세요."
            return
        }
        guard Set(normalizedEntries.map(\.source)).count == normalizedEntries.count else {
            localError = "같은 원문을 두 번 등록할 수 없습니다."
            return
        }

        Task {
            await store.savePronunciationDictionary(
                id: draftID,
                name: normalizedName,
                language: normalizedLanguage,
                entries: normalizedEntries
            )
            guard store.lastError == nil,
                  let saved = store.pronunciationDictionaries.first(where: { $0.name == normalizedName }) else {
                return
            }
            selectedID = saved.id
            load(saved)
        }
    }

    private func deleteCurrentDictionary() {
        guard let draftID,
              let dictionary = store.pronunciationDictionaries.first(where: { $0.id == draftID }) else {
            return
        }
        Task {
            await store.delete(dictionary)
            guard store.lastError == nil else { return }
            if let first = store.pronunciationDictionaries.first {
                selectedID = first.id
                load(first)
            } else {
                beginNewDictionary()
            }
        }
    }
}
