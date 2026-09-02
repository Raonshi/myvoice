import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        NavigationSplitView {
            List(SidebarItem.allCases, selection: $store.selection) { item in
                Label(item.rawValue, systemImage: item.symbol).tag(item)
            }
            .navigationTitle("MyVoice")
            .navigationSplitViewColumnWidth(min: 180, ideal: 210)
        } detail: {
            Group {
                switch store.selection ?? .overview {
                case .overview: OverviewView()
                case .generate: GenerateView()
                case .enroll: EnrollView()
                case .pronunciationDictionaries: PronunciationDictionariesView()
                case .voices: VoicesView()
                case .jobs: JobsView()
                case .doctor: DoctorView()
                }
            }
            .frame(minWidth: 650, minHeight: 520)
        }
        .toolbar {
            ToolbarItem {
                if store.isWorking { ProgressView().controlSize(.small) }
            }
            ToolbarItem {
                Button { Task { await store.refresh() } } label: {
                    Label("새로 고침", systemImage: "arrow.clockwise")
                }
                .disabled(store.isWorking)
            }
        }
        .safeAreaInset(edge: .bottom) {
            StatusBar()
        }
        .alert("작업을 완료하지 못했습니다", isPresented: Binding(
            get: { store.lastError != nil },
            set: { if !$0 { store.lastError = nil } }
        )) { Button("확인", role: .cancel) {} } message: {
            Text(store.lastError ?? "알 수 없는 오류")
        }
        .task { if store.voices.isEmpty && store.jobs.isEmpty { await store.refresh() } }
    }
}

private struct StatusBar: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: store.lastError == nil ? "checkmark.circle" : "exclamationmark.triangle")
            Text(store.activity)
            Spacer()
            Text("v\(store.version)").foregroundStyle(.secondary)
        }
        .font(.caption)
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(.bar)
    }
}
