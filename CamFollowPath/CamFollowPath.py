import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging
import numpy

#
# CamFollowPath
#

class CamFollowPath(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "CamFollowPath" # TODO make this more human readable by adding spaces
    self.parent.categories = ["Examples"]
    self.parent.dependencies = []
    self.parent.contributors = ["John Doe (AnyWare Corp.)"] # replace with "Firstname Lastname (Organization)"
    self.parent.helpText = """
    This is an example of scripted loadable module bundled in an extension.
    It performs a simple thresholding on the input volume and optionally captures a screenshot.
    """
    self.parent.acknowledgementText = """
    This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc.
    and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""" # replace with organization, grant and thanks.

#
# CamFollowPathWidget
#

class CamFollowPathWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent = None):
    ScriptedLoadableModuleWidget.__init__(self, parent)

    self.logic = CamFollowPathLogic()

    self.camTransformNodeId = None
    self.camTransformObserverTag = None

    self.pathToToolTransformNodeId = None

    self.fiducialNodeId = None


  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Instantiate and connect widgets ...

    #
    # Parameters Area
    #
    parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    parametersCollapsibleButton.text = "Parameters"
    self.layout.addWidget(parametersCollapsibleButton)

    # Layout within the dummy collapsible button
    parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)

    #
    # input fiducials selector
    #
    self.inputFiducialSelector = slicer.qMRMLNodeComboBox()
    self.inputFiducialSelector.nodeTypes = ["vtkMRMLMarkupsFiducialNode"]
    self.inputFiducialSelector.selectNodeUponCreation = True
    self.inputFiducialSelector.addEnabled = True
    self.inputFiducialSelector.removeEnabled = True
    self.inputFiducialSelector.noneEnabled = True
    self.inputFiducialSelector.showHidden = False
    self.inputFiducialSelector.showChildNodeTypes = False
    self.inputFiducialSelector.setMRMLScene(slicer.mrmlScene)
    self.inputFiducialSelector.setToolTip("Pick the input to the algorithm.")
    parametersFormLayout.addRow("Fiducial list: ", self.inputFiducialSelector)

    # input transform selector

    self.inputTransformSelector = slicer.qMRMLNodeComboBox()
    self.inputTransformSelector.nodeTypes = ["vtkMRMLLinearTransformNode"]
    self.inputTransformSelector.selectNodeUponCreation = True
    self.inputTransformSelector.addEnabled = True
    self.inputTransformSelector.removeEnabled = True
    self.inputTransformSelector.noneEnabled = True
    self.inputTransformSelector.showHidden = False
    self.inputTransformSelector.showChildNodeTypes = False
    self.inputTransformSelector.setMRMLScene(slicer.mrmlScene)
    self.inputTransformSelector.setToolTip("Pick the tracked transform for the camera.")
    parametersFormLayout.addRow("Input transform (Tool): ", self.inputTransformSelector)

    # output transform selector

    self.outputTransformSelector = slicer.qMRMLNodeComboBox()
    self.outputTransformSelector.nodeTypes = ["vtkMRMLLinearTransformNode"]
    self.outputTransformSelector.selectNodeUponCreation = True
    self.outputTransformSelector.addEnabled = True
    self.outputTransformSelector.removeEnabled = True
    self.outputTransformSelector.renameEnabled = True
    self.outputTransformSelector.noneEnabled = True
    self.outputTransformSelector.showHidden = False
    self.outputTransformSelector.showChildNodeTypes = False
    self.outputTransformSelector.setMRMLScene(slicer.mrmlScene)
    self.outputTransformSelector.setToolTip("Pick the filtered transform for the camera.")
    parametersFormLayout.addRow("Output transform (PathToTool): ", self.outputTransformSelector)

    # range spinbox

    self.rangeSpinBox = ctk.ctkDoubleSpinBox()
    self.rangeSpinBox.setValue(10.0)
    parametersFormLayout.addRow("Snap range (mm): ", self.rangeSpinBox)

    # check box

    self.snapTransformCheckBox = qt.QCheckBox()
    self.snapTransformCheckBox.checked = 0
    self.snapTransformCheckBox.setToolTip("If checked, transform will be snapped to fiducial line.")
    parametersFormLayout.addRow("Enable snap to line", self.snapTransformCheckBox)

    # connections
    self.snapTransformCheckBox.connect("stateChanged(int)", self.onCheckBoxStateChanged)

    # Add vertical spacer
    self.layout.addStretch(1)


  def cleanup(self):
    pass


  def onCheckBoxStateChanged(self):

    # If unchecked, stop observing

    if self.snapTransformCheckBox.checked == False:
      if self.camTransformNodeId == None:
        return
      camTransformNode = slicer.util.getNode(self.camTransformNodeId)
      if camTransformNode == None:
        return
      camTransformNode.RemoveObserver(self.camTransformObserverTag)
      self.camTransformObserverTag = None
      self.camTransformNodeId = None
      return

    # If checked, start observing

    fiducialNode = self.inputFiducialSelector.currentNode()
    if fiducialNode == None:
      self.fiducialNodeId = None
      return
    self.fiducialNodeId = fiducialNode.GetID()

    closestToRasNode = self.outputTransformSelector.currentNode()
    if closestToRasNode == None:
      return
    self.pathToToolTransformNodeId = closestToRasNode.GetID()

    camTransformNode = self.inputTransformSelector.currentNode()
    if camTransformNode == None:
      self.camTransformNodeId = None
      return

    self.camTransformNodeId = camTransformNode.GetID()
    self.camTransformObserverTag = camTransformNode.AddObserver(slicer.vtkMRMLTransformNode.TransformModifiedEvent, self.snapCamTransform)


  def snapCamTransform(self, observer, eventid):

    fiducials = slicer.util.getNode(self.fiducialNodeId)
    if fiducials == None:
      logging.error('Invalid fiducial node ID')
      return

    # Compute position of the camera

    camToRas = slicer.util.getNode(self.camTransformNodeId)
    if camToRas == None:
      logging.error('Transform node ID error: ' + self.camTransformNodeId)
      return

    camToRasTransform = vtk.vtkGeneralTransform()
    camToRas.GetTransformToWorld(camToRasTransform)
    camPosition_Cam = numpy.array([0.0, 0.0, 0.0])
    camPosition_Ras = camToRasTransform.TransformFloatPoint(camPosition_Cam)

    closestCurvePoint = numpy.array([0.0, 0.0, 0.0])
    self.logic.closestPointFiducials(fiducials, camPosition_Ras, closestCurvePoint)

    pathToCamTranslation = closestCurvePoint - camPosition_Ras[:3]

    range = self.rangeSpinBox.value
    d = numpy.linalg.norm(pathToCamTranslation)

    closestToCamTransform = vtk.vtkTransform()

    if d > range:
      closestToCamTransform.Identity()
    else:
      closestToCamTransform.Translate(pathToCamTranslation[0], pathToCamTranslation[1], pathToCamTranslation[2])

    closestToCamTransform.Update()

    if self.pathToToolTransformNodeId == None:
      logging.error('Output transform ID not found')
      return
    pathToTool = slicer.util.getNode(self.pathToToolTransformNodeId)
    if pathToTool == None:
      logging.error('Output not specified')
      return

    pathToTool.SetAndObserveTransformToParent(closestToCamTransform)


# CamFollowPathLogic

class CamFollowPathLogic(ScriptedLoadableModuleLogic):

  def __init__(self):
    pass

  def closestPointFiducials(self, fid, p, closestPoint):
    n = fid.GetNumberOfFiducials()
    if n < 2:
      return False
    minDistance = 9000000
    for i in range(n - 1):
      l1 = [0, 0, 0]
      l2 = [0, 0, 0]
      fid.GetNthFiducialPosition(i, l1)
      fid.GetNthFiducialPosition(i + 1, l2)
      t = vtk.mutable(0)
      cp = [0, 0, 0]
      d = vtk.vtkLine.DistanceToLine(p, l1, l2, t, cp)
      if d < minDistance:
        minDistance = d
        for j in range(3):
          closestPoint[j] = cp[j]
    return True


class CamFollowPathTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)


  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_CamFollowPath1()


  def test_CamFollowPath1(self):

    self.delayDisplay("Starting the test")

    f = slicer.vtkMRMLMarkupsFiducialNode()
    f.SetName( 'P' )
    slicer.mrmlScene.AddNode( f )

    import math

    x = 0.0
    y = 0.0
    z = 0.0
    n = 20
    for i in range( n ):
      x = float( i ) / float( n ) * 100
      y = math.sin( float( i ) / float( n ) * 6.28 )* 30.0
      z = 0.0
      f.AddFiducial( x, y, z )

    # Create a coordinate model

    createModelsLogic = slicer.modules.createmodels.logic()
    cModel = createModelsLogic.CreateCoordinate(20,2)
    cModel.SetName('CamCoordinateModel')
    cModel.GetDisplayNode().SetColor(1,1,0)

    # Create a transform

    cTransformNode = slicer.vtkMRMLLinearTransformNode()
    cTransformNode.SetName('CamToRas')
    slicer.mrmlScene.AddNode(cTransformNode)

    cModel.SetAndObserveTransformNodeID(cTransformNode.GetID())

    # Create output transform with coordinate model

    closestModel = createModelsLogic.CreateCoordinate(20,2)
    closestModel.SetName('ClosestCoordinateModel')
    closestModel.GetDisplayNode().SetColor(0,1,1)

    closestToRasTransformNode = slicer.vtkMRMLLinearTransformNode()
    closestToRasTransformNode.SetName('ClosestToRas')
    slicer.mrmlScene.AddNode(closestToRasTransformNode)
    closestToRasTransformNode.SetAndObserveTransformNodeID(cTransformNode.GetID())

    closestModel.SetAndObserveTransformNodeID(closestToRasTransformNode.GetID())



