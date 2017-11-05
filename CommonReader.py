# Copyright (c) 2017 Thomas Karl Pietrowski

# Buildins
import os
import tempfile
import threading
import uuid
import platform

# Uranium/Cura
from UM.Application import Application
from UM.Mesh.MeshReader import MeshReader
from UM.Logger import Logger
from UM.PluginRegistry import PluginRegistry

if platform.system() == "Windows":
    from .SystemUtils import convertDosPathIntoLongPath


class CommonReader(MeshReader):
    conversion_lock = threading.Lock()

    def __init__(self,
                 app_friendly_name):
        super().__init__()
        
        # Setting default aka fallback
        self._default_app_friendly_name = app_friendly_name
        
        # By default allow no parallel execution. Just to be failsave...
        self._parallel_execution_allowed = False
        
        # Recommeded order of formats to export to
        

        # Start/stop behaviour

        # Technically neither preloading nor keeping the instance up, is possible, since Cura calls the file reader from different/new threads
        # The error when trying to use it here is:
        # > pywintypes.com_error: (-2147417842, 'The application called an interface that was marshalled for a different thread.', None, None)
        self._app_preload = False
        self._app_keep_running = False

        """
        if self._app_preload and not self._app_keep_running:
            self._app_keep_running = True
        """

        # Preparations
        """
        if self._app_preload:
            Logger.log("d", "Preloading %s..." %(self._app_friendlyName))
            self.startApp()
        """

        #Logger.log("d", "Looking for readers...")
        #self.__init_builtin_readers__()

    #def __init_builtin_readers__(self):
    #    self._file_formats_first_choice = [] # Ordered list of preferred formats
    #    self._reader_for_file_format = {}
    #
    #    # Trying 3MF first because it describes the model much better..
    #    # However, this is untested since this plugin was only tested with STL support
    #    if PluginRegistry.getInstance().isActivePlugin("3MFReader"):
    #        self._reader_for_file_format["3mf"] = PluginRegistry.getInstance().getPluginObject("3MFReader")
    #        self._file_formats_first_choice.append("3mf")
    #
    #    if PluginRegistry.getInstance().isActivePlugin("STLReader"):
    #        self._reader_for_file_format["stl"] = PluginRegistry.getInstance().getPluginObject("STLReader")
    #        self._file_formats_first_choice.append("stl")
    #
    #    if not len(self._reader_for_file_format):
    #        Logger.log("d", "Could not find any reader for (probably) supported file formats!")

    @property
    def _app_names(self):
        return []

    @property
    def _file_formats_first_choice(self):
        return []

    @property
    def _reader_for_file_format(self):
        _reader_for_file_format = {}

        # Trying 3MF first because it describes the model much better..
        # However, this is untested since this plugin was only tested with STL support
        if PluginRegistry.getInstance().isActivePlugin("STLReader"):
            _reader_for_file_format["stl"] = PluginRegistry.getInstance().getPluginObject("STLReader")

        if not len(_reader_for_file_format):
            Logger.log("d", "Could not find any reader for (probably) supported file formats!")

        return _reader_for_file_format

    def checkApp(self):
        raise NotImplementedError("Checking app is not implemented!")

    def getAppVisible(self, state):
        raise NotImplementedError("Toggle for visibility not implemented!")

    def setAppVisible(self, state, options):
        raise NotImplementedError("Toggle for visibility not implemented!")

    def closeApp(self, options):
        raise NotImplementedError("Procedure how to close your app is not implemented!")

    def openForeignFile(self, options):
        "This function shall return options again. It optionally contains other data, which is needed by the reader for other tasks later."
        raise NotImplementedError("Opening files is not implemented!")

    def exportFileAs(self, model, options):
        raise NotImplementedError("Exporting files is not implemented!")

    def closeForeignFile(self, options):
        raise NotImplementedError("Closing files is not implemented!")

    def nodePostProcessing(self, node):
        return node

    def readCommon(self, file_path):
        "Common steps for each read"

        options = {"foreignFile": file_path,
                   "foreignFormat": os.path.splitext(file_path)[1],
                   }

        # Let's convert only one file at a time!
        self.conversion_lock.acquire()
        
        # Append all formats which are not preferred to the end of the list
        options["fileFormats"] = self._file_formats_first_choice
        for file_format in self._reader_for_file_format.keys():
            if file_format not in options["fileFormats"]:
                options["fileFormats"].append(file_format)
        
        return options
        
    def readOnSingleAppLayer(self, options):
        scene_node = None
        
        # Tell the loaded application to open a file...
        Logger.log("d", "... and opening file.")
        options = self.openForeignFile(options)
                   
        # Trying to convert into all formats 1 by 1 and continue with the successful export
        Logger.log("i", "Trying to convert into one of: %s", options["fileFormats"])
        for file_format in options["fileFormats"]:
            Logger.log("d", "Trying to convert <%s>...", os.path.split(options["foreignFile"])[1])
            options["tempType"] = file_format
        
            # Creating a new unique filename in the temporary directory..
            tempdir = tempfile.tempdir
            if platform.system() == "Windows":
                tempdir = convertDosPathIntoLongPath(tempdir)
            options["tempFile"] = os.path.join(tempdir,
                                               "{}.{}".format(uuid.uuid4(), file_format.upper()),
                                               )
            Logger.log("d", "... into '%s' format: <%s>", file_format, options["tempFile"])
            try:
                self.exportFileAs(options)
            except:
                Logger.logException("e", "Could not export <%s> into '%s'.", options["foreignFile"], file_format)
                continue

            if os.path.isfile(options["tempFile"]):
                Logger.log("d", "Found temporary file!")
            else:
                Logger.log("c", "Temporary file not found after export!")
                continue
        
            # Opening the resulting file in Cura
            try:
                reader = Application.getInstance().getMeshFileHandler().getReaderForFile(options["tempFile"])
                if not reader:
                    Logger.log("d", "Found no reader for %s. That's strange...", file_format)
                    continue
                Logger.log("d", "Using reader: %s", reader.getPluginId())
                scene_node = reader.read(options["tempFile"])
                break
            except:
                Logger.logException("e", "Failed to open exported <%s> file in Cura!", file_format)
                continue
            finally:
                # Whatever happens, remove the temp_file again..
                Logger.log("d", "Removing temporary %s file, called <%s>", file_format, options["tempFile"])
                os.remove(options["tempFile"])
                # Pass to the node the correct aka original filename
        
        return scene_node

    def readOnMultipleAppLayer(self, options):
        scene_node = None
        for app_name in self._app_names:
            options["app_name"] = app_name
            
            # Preparations before starting the application
            self.preStartApp()
            try:
                # Start the app by its name...
                self.startApp(options)
                
                scene_node = self.readOnSingleAppLayer(options)
                if scene_node:
                    # We don't need to test the next application. The result is already there...
                    break
                
            except Exception:
                Logger.logException("e", "Failed to export using '%s'...", app_name)
                # Let's try with the next application...
                continue
            finally:
                # Closing document in the app
                self.closeForeignFile(options)
                # Closing the app again..
                self.closeApp(options)
                # Nuke the instance!
                if "app_instance" in options.keys():
                    del options["app_instance"]
                # .. and finally do some cleanups
                self.postCloseApp()

        self.conversion_lock.release()

        """
        if not scene_node:
            error_message = Message(i18n_catalog.i18nc("@info:status", "Could not open {}!".format(file_path)))
            error_message.show()
            return scene_node
        """
        if not scene_node:
            return scene_node
        elif not isinstance(scene_node, list):
            # This part is needed for reloading converted files into STL - Cura will try otherwise to reopen the temp file, which is already removed.
            mesh_data = scene_node.getMeshData()
            Logger.log("d", "File path in mesh was: %s", mesh_data.getFileName())
            mesh_data = mesh_data.set(file_name = options["foreignFile"])
            scene_node.setMeshData(mesh_data)
            scene_node_list = [scene_node]
        else:
            # Likely the result of an 3MF conversion
            scene_node_list = scene_node

        self.nodePostProcessing(scene_node_list)

        return scene_node