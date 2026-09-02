import AppKit
import SwiftUI

struct JobsView: View {
    @EnvironmentObject private var store: AppStore
    @State private var selectedID: String?
    @State private var regenerating: SpeechSegment?
    @State private var replacementText = ""

    private var selected: GenerationJob? { store.jobs.first { $0.id == selectedID } }

    var body: some View {
        HSplitView {
            List(store.jobs, selection: $selectedID) { job in
                VStack(alignment: .leading, spacing: 4) {
                    Text(job.id).lineLimit(1).font(.headline)
                    HStack { Text(job.voiceName); Spacer(); StatusBadge(status: job.status) }
                }.tag(job.id).padding(.vertical, 2)
            }.frame(minWidth: 275, idealWidth: 310)

            Group {
                if let job = selected {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(job.id).font(.title2.bold()).textSelection(.enabled)
                                Text(job.outputPath).foregroundStyle(.secondary).textSelection(.enabled)
                            }
                            Spacer()
                            Button("Finder에서 보기") { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: job.outputPath)]) }
                            if job.status != "completed" {
                                Button("재개") { Task { await store.resume(job) } }.buttonStyle(.borderedProminent)
                            }
                        }
                        Table(job.segments) {
                            TableColumn("#") { Text($0.order.formatted()).monospacedDigit() }.width(35)
                            TableColumn("상태") { StatusBadge(status: $0.status) }.width(85)
                            TableColumn("텍스트") { Text($0.normalizedText).lineLimit(2) }
                            TableColumn("작업") { segment in
                                Button("다시 생성") { replacementText = segment.normalizedText; regenerating = segment }
                                    .disabled(store.isWorking)
                            }.width(85)
                        }
                        if let error = job.error { Text(error).foregroundStyle(.red).textSelection(.enabled) }
                    }.padding(22)
                } else {
                    ContentUnavailableView("생성 작업을 선택하세요", systemImage: "clock.arrow.circlepath")
                }
            }.frame(minWidth: 450)
        }
        .navigationTitle("생성 작업")
        .onAppear { selectedID = selectedID ?? store.jobs.first?.id }
        .sheet(item: $regenerating) { segment in
            VStack(alignment: .leading, spacing: 16) {
                Text("\(segment.id) 다시 생성").font(.title2.bold())
                TextEditor(text: $replacementText).font(.body).frame(minHeight: 120).border(.separator)
                HStack {
                    Spacer()
                    Button("취소") { regenerating = nil }
                    Button("다시 생성") {
                        if let job = selected { Task { await store.regenerate(job: job, segment: segment, text: replacementText) } }
                        regenerating = nil
                    }.buttonStyle(.borderedProminent)
                }
            }.padding(22).frame(width: 520)
        }
    }
}
