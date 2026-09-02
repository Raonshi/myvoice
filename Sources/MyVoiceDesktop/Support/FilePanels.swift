import AppKit
import UniformTypeIdentifiers

enum FilePanels {
    @MainActor static func chooseDirectory() -> String? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        return panel.runModal() == .OK ? panel.url?.path : nil
    }

    @MainActor static func chooseFile(types: [String]) -> String? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = types.compactMap { UTType(filenameExtension: $0) }
        return panel.runModal() == .OK ? panel.url?.path : nil
    }

    @MainActor static func chooseFiles(types: [String]) -> [String]? {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = types.compactMap { UTType(filenameExtension: $0) }
        return panel.runModal() == .OK ? panel.urls.map(\.path) : nil
    }

    @MainActor static func saveAAC(suggestedName: String = "narration.aac") -> String? {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedName
        if let aac = UTType(filenameExtension: "aac") { panel.allowedContentTypes = [aac] }
        return panel.runModal() == .OK ? panel.url?.path : nil
    }
}
