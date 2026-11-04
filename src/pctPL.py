#list of dependencies needed to run the script

import arcpy
from pctPLFunctions import *

arcpy.env.overwriteOutput = True


#1 - Filepath of geodatabase where analysis will occur. Can be the same 
#as the results geodatabase. MUST USE A GEODATABASE(.gdb)!

Workspace = "C:\\Path\\To\\Analysis\\Geodatabase.gdb"

#2 - Coordinate system using WKID code. a list of wkid codes can be found at:
#https://pro.arcgis.com/en/pro-app/3.4/arcpy/classes/pdf/projected_coordinate_systems.pdf

WKID_Code = 102005

#3 - filepath to folder containing potential sites. IF the folder contains more files
# than needed for the analysis, Use the wildcard_filter to only select files containing
#certain characters. for structuring wildcard filer refer to:
# https://www.w3schools.com/sql/sql_wildcards.asp 

SiteFiles = "C:\\Path\\To\\Analysis\\Site\\Files"
wildcard_filter = ""

#4 - If site files are made up of sites from a single type of analysis you can choose to
#merge the files together by setting the merge file variable to True. set the mergeResults
#variable to the desired name of the output merged files. If site files make up sites 
#from multiple different analyses it is not recommended to merge the files. set mergefiles
#to False to skip merging.

mergefiles = False
mergeResults = "ResultsofMerge"

#5 - Filepath of folder/Geodatabase where results will be saved.

ResultsDir  = "C:\\Path\\To\\Results\\Geodatabase.gdb"

#6 - SubsetSize refers to the size of copied site data that will be used for analysis.
#A SubsetSize of 500,000 will divide the site data into subsets of 500,000 features
#each.

SubsetSize = 500000

#7 - path to public lands file. This file will be copied for use in the analysis. 
#An optional function Removeoverlaps can be ran to remove any overlapping polygons from 
#the copy of the public lands file if removeOverlaps variable is set to True.

PublicLands = "C:\\Path\\To\\Public\\Lands"
rmOverlaps = False

#8 - Optionally a seperate results feature class can be produced in the results directory
#containing only sites with a given percentage of public land. to perform this step
#set HighPctSites to True and set percent to a float between 0 and 1.

HighPctSites = True
percent = .9

# #the main function that calls the custom functions needed to conduct the analysis 

def main():
    output = CheckParameters(Workspace, wildcard_filter, WKID_Code, SiteFiles, ResultsDir, PublicLands)
    SiteFileList = output[0]
    if rmOverlaps:
        PLCopy = Removeoverlaps(output[1])
    else:    
        PLCopy = output[1]
    if HighPctSites:
        MostAgencies = 0
    if mergefiles:
        ListResults = []
    for file in SiteFileList:
        subsets = DivideDataset(file, Workspace , SiteFiles, SubsetSize)
        for subset in subsets:
            lands = PublicLandsinSites(subset,PLCopy)
            AgencyCount = CalculatePctPL(lands,subset)
            if HighPctSites:
                if AgencyCount > MostAgencies:
                    MostAgencies = AgencyCount
        results = MergeResults(subsets,file,ResultsDir, merging=False)
        if not mergefiles:
            if HighPctSites:
                GroupHighPctSites(results,ResultsDir,percent)
                MostAgencies = 0
        else:
            ListResults.append(results)
    if mergefiles:
        MergeResults(ListResults,mergeResults,ResultsDir, merging=True)
        if HighPctSites:
            GroupHighPctSites(mergeResults,ResultsDir,percent)
    return None

#This line tells the python script to run the main function, if you remove this line
#the script will not run.

main()