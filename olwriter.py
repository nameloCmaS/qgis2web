# qgis-ol3 Creates OpenLayers map from QGIS layers
# Copyright (C) 2014 Victor Olaya (volayaf@gmail.com)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import re
from datetime import datetime
from qgis.core import (QgsProject,
                       QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform,
                       QgsRectangle,
                       QgsCsException)
from utils import (exportLayers, replaceInTemplate)
from qgis.utils import iface
from PyQt4.QtCore import Qt
from PyQt4.QtCore import QObject
from PyQt4.QtGui import (QApplication,
                         QCursor)
from olFileScripts import writeFiles, writeHTMLstart, writeScriptIncludes
from olLayerScripts import writeLayersAndGroups
from olScriptStrings import (measureScript,
                             measuringScript,
                             measureControlScript,
                             measureUnitMetricScript,
                             measureUnitFeetScript,
                             measureStyleScript,
                             geolocation,
                             geolocateStyle,
                             geolocationHead,
                             geocodeLinks,
                             geocodeJS,
                             geocodeScript,
                             getGrid,
                             getM2px,
                             getMapUnitLayers)
from olStyleScripts import exportStyles
from writer import (Writer,
                    WriterResult,
                    translator)
from feedbackDialog import Feedback


class OpenLayersWriter(Writer):

    """
    Writer for creation of web maps based on the OpenLayers
    JavaScript library.
    """

    def __init__(self):
        super(OpenLayersWriter, self).__init__()

    @classmethod
    def type(cls):
        return 'openlayers'

    @classmethod
    def name(cls):
        return QObject.tr(translator, 'OpenLayers')

    def write(self, iface, dest_folder, feedback=None):
        if not feedback:
            feedback = Feedback()

        feedback.showFeedback('Creating OpenLayers map...')

        self.preview_file = self.writeOL(iface, feedback,
                                         layers=self.layers,
                                         groups=self.groups,
                                         popup=self.popup,
                                         visible=self.visible,
                                         json=self.json,
                                         clustered=self.cluster,
                                         getFeatureInfo=self.getFeatureInfo,
                                         settings=self.params,
                                         folder=dest_folder)
        result = WriterResult()
        result.index_file = self.preview_file
        result.folder = os.path.dirname(self.preview_file)
        for dirpath, dirnames, filenames in os.walk(result.folder):
            result.files.extend([os.path.join(dirpath, f) for f in filenames])
        return result

    @classmethod
    def writeOL(cls, iface, feedback, layers, groups, popup, visible,
                json, clustered, getFeatureInfo, settings, folder):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        mapSettings = iface.mapCanvas().mapSettings()
        controlCount = 0
        stamp = datetime.now().strftime("%Y_%m_%d-%H_%M_%S_%f")
        folder = os.path.join(folder, 'qgis2web_' + unicode(stamp))
        restrictToExtent = settings["Scale/Zoom"]["Restrict to extent"]
        matchCRS = settings["Appearance"]["Match project CRS"]
        precision = settings["Data export"]["Precision"]
        optimize = settings["Data export"]["Minify GeoJSON files"]
        debugLibs = settings["Data export"]["Use debug libraries"]
        extent = settings["Scale/Zoom"]["Extent"]
        mapbounds = bounds(iface, extent == "Canvas extent", layers, matchCRS)
        fullextent = bounds(iface, False, layers, matchCRS)
        geolocateUser = settings["Appearance"]["Geolocate user"]
        maxZoom = int(settings["Scale/Zoom"]["Max zoom level"])
        minZoom = int(settings["Scale/Zoom"]["Min zoom level"])
        popupsOnHover = settings["Appearance"]["Show popups on hover"]
        highlightFeatures = settings["Appearance"]["Highlight on hover"]
        geocode = settings["Appearance"]["Add address search"]
        measureTool = settings["Appearance"]["Measure tool"]
        addLayersList = settings["Appearance"]["Add layers list"]
        htmlTemplate = settings["Appearance"]["Template"]
        layerSearch = unicode(settings["Appearance"]["Layer search"])
        searchLayer = settings["Appearance"]["Search layer"]
        mapLibLocn = settings["Data export"]["Mapping library location"]

        writeFiles(folder, restrictToExtent, feedback, debugLibs)
        exportLayers(iface, layers, folder, precision, optimize,
                     popup, json, restrictToExtent, extent, feedback, matchCRS)
        mapUnitsLayers = exportStyles(layers, folder, clustered)
        mapUnitLayers = getMapUnitLayers(mapUnitsLayers)
        osmb = writeLayersAndGroups(layers, groups, visible, folder, popup,
                                    settings, json, matchCRS, clustered,
                                    getFeatureInfo, iface, restrictToExtent,
                                    extent, mapbounds,
                                    mapSettings.destinationCrs().authid())
        (jsAddress, cssAddress, layerSearch,
         controlCount) = writeHTMLstart(settings, controlCount, osmb,
                                        mapLibLocn, layerSearch, searchLayer,
                                        feedback, debugLibs)
        (geojsonVars, wfsVars, styleVars) = writeScriptIncludes(layers,
                                                                json, matchCRS)
        popupLayers = "popupLayers = [%s];" % ",".join(
            ['1' for field in popup])
        project = QgsProject.instance()
        controls = getControls(project, measureTool, geolocateUser)
        layersList = getLayersList(addLayersList)
        pageTitle = project.title()
        backgroundColor = getBackground(mapSettings)
        (geolocateCode, controlCount) = geolocateStyle(geolocateUser,
                                                       controlCount)
        backgroundColor += geolocateCode
        mapextent = "extent: %s," % mapbounds if restrictToExtent else ""
        onHover = unicode(popupsOnHover).lower()
        highlight = unicode(highlightFeatures).lower()
        highlightFill = mapSettings.selectionColor().name()
        (proj, proj4, view) = getCRSView(mapextent, fullextent, maxZoom,
                                         minZoom, matchCRS, mapSettings)
        (measureControl, measuring, measure, measureUnit, measureStyle,
         controlCount) = getMeasure(measureTool, controlCount)
        geolocateHead = geolocationHead(geolocateUser)
        geolocate = geolocation(geolocateUser)
        geocodingLinks = geocodeLinks(geocode)
        geocodingJS = geocodeJS(geocode)
        geocodingScript = geocodeScript(geocode)
        m2px = getM2px(mapUnitsLayers)
        (extracss, controlCount) = getCSS(geocode, geolocateUser, controlCount)
        ol3layerswitcher = getLayerSwitcher()
        ol3popup = getPopup()
        ol3qgis2webjs = getJS(osmb)
        ol3layers = getLayers()
        mapSize = iface.mapCanvas().size()
        exp_js = getExpJS()
        grid = getGrid(project)
        values = {"@PAGETITLE@": pageTitle,
                  "@CSSADDRESS@": cssAddress,
                  "@EXTRACSS@": extracss,
                  "@JSADDRESS@": jsAddress,
                  "@MAP_WIDTH@": unicode(mapSize.width()) + "px",
                  "@MAP_HEIGHT@": unicode(mapSize.height()) + "px",
                  "@OL3_STYLEVARS@": styleVars,
                  "@OL3_BACKGROUNDCOLOR@": backgroundColor,
                  "@OL3_POPUP@": ol3popup,
                  "@OL3_GEOJSONVARS@": geojsonVars,
                  "@OL3_WFSVARS@": wfsVars,
                  "@OL3_PROJ4@": proj4,
                  "@OL3_PROJDEF@": proj,
                  "@OL3_GEOCODINGLINKS@": geocodingLinks,
                  "@OL3_GEOCODINGJS@": geocodingJS,
                  "@QGIS2WEBJS@": ol3qgis2webjs,
                  "@OL3_LAYERSWITCHER@": ol3layerswitcher,
                  "@OL3_LAYERS@": ol3layers,
                  "@OL3_MEASURESTYLE@": measureStyle,
                  "@EXP_JS@": exp_js,
                  "@LEAFLET_ADDRESSCSS@": "",
                  "@LEAFLET_MEASURECSS@": "",
                  "@LEAFLET_EXTRAJS@": "",
                  "@LEAFLET_ADDRESSJS@": "",
                  "@LEAFLET_MEASUREJS@": "",
                  "@LEAFLET_CRSJS@": "",
                  "@LEAFLET_LAYERSEARCHCSS@": "",
                  "@LEAFLET_LAYERSEARCHJS@": "",
                  "@LEAFLET_CLUSTERCSS@": "",
                  "@LEAFLET_CLUSTERJS@": ""}
        with open(os.path.join(folder, "index.html"), "w") as f:
            htmlTemplate = htmlTemplate
            if htmlTemplate == "":
                htmlTemplate = "basic"
            templateOutput = replaceInTemplate(
                htmlTemplate + ".html", values)
            templateOutput = re.sub(r'\n[\s_]+\n', '\n', templateOutput)
            f.write(templateOutput.encode('utf-8'))
        values = {"@GEOLOCATEHEAD@": geolocateHead,
                  "@BOUNDS@": mapbounds,
                  "@CONTROLS@": ",".join(controls),
                  "@LAYERSLIST@": layersList,
                  "@POPUPLAYERS@": popupLayers,
                  "@VIEW@": view,
                  "@LAYERSEARCH@": layerSearch,
                  "@ONHOVER@": onHover,
                  "@DOHIGHLIGHT@": highlight,
                  "@HIGHLIGHTFILL@": highlightFill,
                  "@GEOLOCATE@": geolocate,
                  "@GEOCODINGSCRIPT@": geocodingScript,
                  "@MEASURECONTROL@": measureControl,
                  "@MEASURING@": measuring,
                  "@MEASURE@": measure,
                  "@MEASUREUNIT@": measureUnit,
                  "@GRID@": grid,
                  "@M2PX@": m2px,
                  "@MAPUNITLAYERS@": mapUnitLayers}
        with open(os.path.join(folder, "resources", "qgis2web.js"),
                  "w") as f:
            out = replaceInScript("qgis2web.js", values)
            f.write(out.encode("utf-8"))
        QApplication.restoreOverrideCursor()
        return os.path.join(folder, "index.html")


def replaceInScript(template, values):
    path = os.path.join(os.path.dirname(__file__), "resources", template)
    with open(path) as f:
        lines = f.readlines()
    s = "".join(lines)
    for name, value in values.iteritems():
        s = s.replace(name, value)
    return s


def bounds(iface, useCanvas, layers, matchCRS):
    if useCanvas:
        canvas = iface.mapCanvas()
        canvasCrs = canvas.mapSettings().destinationCrs()
        if not matchCRS:
            transform = QgsCoordinateTransform(canvasCrs,
                                               QgsCoordinateReferenceSystem(
                                                   "EPSG:3857"))
            try:
                extent = transform.transform(canvas.extent())
            except QgsCsException:
                extent = QgsRectangle(-20026376.39, -20048966.10,
                                      20026376.39, 20048966.10)
        else:
            extent = canvas.extent()
    else:
        extent = None
        for layer in layers:
            if not matchCRS:
                epsg3857 = QgsCoordinateReferenceSystem("EPSG:3857")
                transform = QgsCoordinateTransform(layer.crs(), epsg3857)
                try:
                    layerExtent = transform.transform(layer.extent())
                except QgsCsException:
                    layerExtent = QgsRectangle(-20026376.39, -20048966.10,
                                               20026376.39, 20048966.10)
            else:
                layerExtent = layer.extent()
            if extent is None:
                extent = layerExtent
            else:
                extent.combineExtentWith(layerExtent)

    return "[%f, %f, %f, %f]" % (extent.xMinimum(), extent.yMinimum(),
                                 extent.xMaximum(), extent.yMaximum())


def getControls(project, measureTool, geolocateUser):
    controls = ['expandedAttribution']
    if project.readBoolEntry("ScaleBar", "/Enabled", False)[0]:
        controls.append("new ol.control.ScaleLine({})")
    if measureTool != "None":
        controls.append('new measureControl()')
    if geolocateUser:
        controls.append('new geolocateControl()')
    return controls


def getLayersList(addLayersList):
    if (addLayersList and addLayersList != "" and addLayersList != "None"):
        layersList = """
var layerSwitcher = new ol.control.LayerSwitcher({tipLabel: "Layers"});
map.addControl(layerSwitcher);"""
        if addLayersList == "Expanded":
            layersList += """
layerSwitcher.hidePanel = function() {};
layerSwitcher.showPanel();
"""
    else:
        layersList = ""
    return layersList


def getBackground(mapSettings):
    return """
        <style>
        html, body {{
            background-color: {bgcol};
        }}
        </style>
""".format(bgcol=mapSettings.backgroundColor().name())


def getCRSView(mapextent, fullextent, maxZoom, minZoom, matchCRS, mapSettings):
    units = ['m', 'ft', 'degrees', '']
    proj4 = ""
    proj = ""
    view = "%s maxZoom: %d, minZoom: %d" % (mapextent, maxZoom, minZoom)
    if matchCRS:
        proj4 = """
<script src="resources/proj4.js">"""
        proj4 += "</script>"
        proj = "<script>proj4.defs('{epsg}','{defn}');</script>".format(
            epsg=mapSettings.destinationCrs().authid(),
            defn=mapSettings.destinationCrs().toProj4())
        unit = mapSettings.destinationCrs().mapUnits()
        view += """, projection: new ol.proj.Projection({
            code: '%s',
            extent: %s,
            units: '%s'})""" % (mapSettings.destinationCrs().authid(),
                                fullextent, units[unit])
    return (proj, proj4, view)


def getMeasure(measureTool, controlCount):
    if measureTool != "None":
        measureControl = measureControlScript()
        measuring = measuringScript()
        measure = measureScript()
        if measureTool == "Imperial":
            measureUnit = measureUnitFeetScript()
        else:
            measureUnit = measureUnitMetricScript()
        measureStyle = measureStyleScript(controlCount)
        controlCount = controlCount + 1
    else:
        measureControl = ""
        measuring = ""
        measure = ""
        measureUnit = ""
        measureStyle = ""
    return (measureControl, measuring, measure, measureUnit, measureStyle,
            controlCount)


def getCSS(geocode, geolocateUser, controlCount):
    extracss = """
        <link rel="stylesheet" """
    extracss += """href="./resources/ol3-layerswitcher.css">
        <link rel="stylesheet" """
    extracss += """href="./resources/qgis2web.css">"""
    if geocode:
        geocodePos = 65 + (controlCount * 35)
        extracss += """
        <style>
        .ol-geocoder.gcd-gl-container {
            top: %dpx!important;
        }
        .ol-geocoder .gcd-gl-btn {
            width: 21px!important;
            height: 21px!important;
        }
        </style>""" % geocodePos
    if geolocateUser:
        extracss += """
        <link rel="stylesheet" href="http://maxcdn.bootstrapcdn.com/"""
        extracss += """font-awesome/4.6.3/css/font-awesome.min.css">"""
    return (extracss, controlCount)


def getLayerSwitcher():
    return """
        <script src="./resources/ol3-layerswitcher.js"></script>"""


def getPopup():
    return """<div id="popup" class="ol-popup">
                <a href="#" id="popup-closer" class="ol-popup-closer"></a>
                <div id="popup-content"></div>
            </div>"""


def getJS(osmb):
    ol3qgis2webjs = """<script src="./resources/qgis2web.js"></script>
        <script src="./resources/Autolinker.min.js"></script>"""
    if osmb != "":
        ol3qgis2webjs += """
        <script>{osmb}</script>""".format(osmb=osmb)
    return ol3qgis2webjs


def getLayers():
    return """
        <script src="./layers/layers.js" type="text/javascript"></script>"""


def getExpJS():
    return """
        <script src="resources/qgis2web_expressions.js"></script>"""
