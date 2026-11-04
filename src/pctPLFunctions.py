import arcpy
from ast import literal_eval
from ntpath import basename
from os import listdir
from pathlib import Path

def CheckParameters (workspace:str, wildcard:str, WKID_Code:int, sitesfiles:str, resultsdir:str, PublicLands:str):
    '''
    Checks that entered parameters are valid for use in analysis. A copy of the
    public lands feature class is created in the workspace geodatabase if one does
    not already exist.

    Input: listed variable parameters in the header of main script
    Output: a list containing 2 objects. the list of sites files to process
    and a copy of the public lands feature class.
    '''
    #check if workspace is an existing geodatabase at given path
    if not Path(workspace).exists():
        raise ValueError("Workspace path does not exist")

    if not workspace.endswith("gdb"):
        raise ValueError("Selected workspace is not a geodatabase")
    
    #set workspace as arcpy environment
    arcpy.env.workspace = workspace

    #ensure WKID code exists
    try:
        arcpy.env.outputCoordinateSystem = arcpy.SpatialReference(WKID_Code)
    except RuntimeError:
        raise ValueError("WKID Code is not recognized")
   
    #check if sites files exist at given path
    if not Path(sitesfiles).exists():
        raise ValueError("Path to sites files does not exist")
    
    #this code block gathers the files from sites file folder into a list, if the list 
    #contains the files you want to analyze type "y" when prompted, if not type "n" 
    # and the program will end.
    arcpy.env.workspace = sitesfiles
    if sitesfiles.endswith("gdb"):
        #for gdb
        getfiles = arcpy.ListFeatureClasses(wildcard)
    else:
        #for folder
        getfiles = listdir(sitesfiles)
    #Prompt user to confirm that files listed are the files meant for analysis
    print(getfiles)
    print('')
    print("Determine the Public Land Percentage for these files(yes/no)?")
    arcpy.env.workspace = workspace
    while True:
        answer = input()
        if answer == 'yes':
            break
        elif answer == 'no':
            raise SystemExit
        else:
            print("invalid response, please type 'yes' to continue or 'no' to exit:" )
    
    #check if results folder or geodatabase exists 
    if not Path(resultsdir).exists():
        raise ValueError("Path to results directory does not exist")
    
    #check if public lands file exists
    if PublicLands.endswith(".shp"):
     file_path = Path(PublicLands)
     if not file_path.is_file():
        raise ValueError("no file exists at this location")    
    else:
        if not arcpy.Exists(PublicLands):
            raise ValueError("Path to publiclands does not exist")
    
    #check if copy of PublicLands data exists in workspace geodatabase
    #create copy if not
    PLcopy = basename(PublicLands) + "copy"
    if not arcpy.Exists(PLcopy):
        print(f"{PLcopy} does not exist")
        print("copying...\n\t{}\n\tto\n\t{}".format(PublicLands,PLcopy))
        #copy features
        copy_results = arcpy.management.CopyFeatures(PublicLands,PLcopy)
        print(copy_results.getMessages())   
    else:
        print("{} exists!".format(PLcopy))
    arcpy.management.AddSpatialIndex(PLcopy)
    #returns a list of files for analysis and the public land copy
    return [getfiles, PLcopy]

def Removeoverlaps(PublicLandsCopy):
    '''
    Identify and remove overlapping features with > 0 Shape_Area. Largest overlapping features
    are preserved while all other features are clipped using overlap polygon. THIS FUNCTION WILL 
    MODIFY FEATURES IN INPUT FILE, BE SURE TO USE A COPY OF DATA TO AVOID ALTERING 
    ORIGINAL FEATURES. 

    Input: copy of public lands 
    Output: modified copy of public lands
    '''
    #create list of all existing overlaps > 0 in area. List contains geometries of 
    #said features.
    overlaps = "overlaps"
    arcpy.intelligence.FindOverlaps(PublicLandsCopy, overlaps, "cent")
    overlapfield = ["SHAPE@","Shape_Area"]
    count = arcpy.management.GetCount(overlaps)
    if count > 0:
        fieldList = ["OBJECTID","SHAPE@","Shape_Area"]
        geom_list = []
        with arcpy.da.SearchCursor(overlaps, overlapfield) as searchRows:
            for searchRow in searchRows:
                if searchRow[0] != None and searchRow[1] != 0:
                    geom_list.append(searchRow[0])
        #iterate through list of overlap geometries
        for polygon in geom_list:        
            largestArea = 0
            featureid = 0
            #identify largest feature that intersects with overlap polygon
            with arcpy.da.SearchCursor(PublicLandsCopy, fieldList, spatial_filter=polygon,spatial_relationship="INTERSECTS") as checkareas:
                for areas in checkareas:
                    if areas[2] > largestArea:
                        largestArea = areas[2]
                        featureid = areas[0]
            #preserve largest feature, use difference method to clip remaining features
            with arcpy.da.UpdateCursor(PublicLandsCopy, fieldList, spatial_filter=polygon,spatial_relationship="INTERSECTS") as updateRows:
                    for updateRow in updateRows:
                        if updateRow[0] != featureid:
                            try:
                                updateRow[1] = updateRow[1].difference(polygon)
                            except:
                                print("Polygon has no geometry")
                            updateRows.updateRow(updateRow)
    return PublicLandsCopy
#break up shapefile into 500k or smaller chunks
def DivideDataset(sitesfile:str, workspace:str, sitefiles:str, breakpoint:int):
    '''
    Copies sites file into smaller datasets for faster processing

    Inputs: sitesfile = feature class of site locations
            breakpoint = Desired size of each smaller dataset
    Output: list of created feature classes ("subsets")
    '''
    #determine how many subsets exist in the file
    arcpy.env.workspace = sitefiles
    feats = arcpy.management.GetCount(sitesfile)
    groupnmb = int(int(feats[0])/breakpoint)
    lastgroup = float(feats[0])%breakpoint
    groups = []
    count = 0
    for i in range(groupnmb):
        count += breakpoint
        groups.append(count)
    count += lastgroup
    groups.append(count)
    print(groups)

    #use list of subsets to create smaller featureclasses using Select Tool
    subsets = []
    for i in range(len(groups)):
        outname = workspace + "\\" + sitesfile + str(i+1)
        if i >= 1:
            expr = "OBJECTID > " + str(groups[i-1]) + " And OBJECTID <= " + str(groups[i]) 
        else:
            expr = "OBJECTID <= " + str(groups[i])
        arcpy.conversion.ExportFeatures(sitesfile, outname, expr)
        arcpy.management.AddSpatialIndex(outname)
        subsets.append(outname)
    print(subsets)
    arcpy.env.workspace = workspace
    #return list of created subset feature classes
    return subsets

def PublicLandsinSites(subset:str, PublicLandcopy:str):
    '''
    Performs a Pairwise Intersect between the Copied Public Lands and the subset
    of the sites data.

    Inputs: subset of sites file, copy of Public Lands feature class

    Output: created feature class containing the portions of public land that
    intersect with sites.
    '''    
    lands = "LandsPublicinLs"
    IntersectResult = arcpy.analysis.PairwiseIntersect([PublicLandcopy,subset], lands,"ALL")
    print(IntersectResult.getMessages())
    return lands

def CalculatePctPL(Lands,subset):
    '''
    Calculates the percent public land coverage for each feature in the sites subset.
    Managing public land agencies and relative percentage of land ownership are also
    included.  

    Inputs: subset of sites file, Public Lands that intersect with sites

    Output: None
    '''  
    #add fields to subset that will hold public lands information
    arcpy.management.AddField(
    in_table=subset,
    field_name="PctPL",
    field_type="FLOAT",
    field_precision=None,
    field_scale=None,
    field_length=None,
    field_alias="PctPL",
    field_is_nullable="NULLABLE",
    field_is_required="NON_REQUIRED",
    field_domain=""
    )
    arcpy.management.AddField(
    in_table=subset,
    field_name="Agencies",
    field_type="TEXT",
    field_precision=None,
    field_scale=None,
    field_length=None,
    field_alias="Agencies",
    field_is_nullable="NULLABLE",
    field_is_required="NON_REQUIRED",
    field_domain=""
    )
    arcpy.management.AddField(
    in_table=subset,
    field_name="AgcyPct",
    field_type="TEXT",
    field_precision=None,
    field_scale=None,
    field_length=None,
    field_alias="AgcyPct",
    field_is_nullable="NULLABLE",
    field_is_required="NON_REQUIRED",
    field_domain=""
    )

    arg = "FID_" + basename(subset)
    sourceFieldsList = [arg, "Shape_Area","ADMIN_AGEN"]

# Build a summary dictionary with unique key values for each subset FID
    valueDict = {}
    with arcpy.da.SearchCursor(Lands, sourceFieldsList) as searchRows:
        for searchRow in searchRows:
            keyValue = searchRow[0]
            if not keyValue in valueDict:
                # assign a new keyValue entry to the dictionary storing a list as first value
                #list will contain three values: total public land area, list of agencies,
                # list of agency-specific area
                valueDict[keyValue] = [searchRow[1], [searchRow[2]],[searchRow[1]]]
            # if key value exists, add area to area sum and agency area(if exists)
            # if agency area does not exist add agency and agency area seperately
            else:
                valueDict[keyValue][0] += searchRow[1]
                try:
                    PositionMatch = valueDict[keyValue][1].index(searchRow[2])
                except:
                    AreaVar = searchRow[1]
                    for i in range(len(valueDict[keyValue][2])):
                        if AreaVar > valueDict[keyValue][2][i]:
                            valueDict[keyValue][2].insert(i, AreaVar)
                            break
                    else:
                        valueDict[keyValue][2].append(AreaVar)
                    Agenvar = searchRow[2]
                    pos = valueDict[keyValue][2].index(AreaVar)
                    valueDict[keyValue][1].insert(pos,Agenvar)

                else:
                    AreaVar = searchRow[1] + valueDict[keyValue][2][PositionMatch]
                    valueDict[keyValue][2][PositionMatch] = AreaVar
    #update created fields with dictionary values               
    updateFieldsList = ["OBJECTID", "Shape_Area","PctPL","Agencies","AgcyPct"]

    with arcpy.da.UpdateCursor(subset, updateFieldsList) as updateRows:
        for updateRow in updateRows:
            # store the Join value of the row being updated in a keyValue variable
            keyValue = updateRow[0]
            
            # verify that the keyValue is in the Dictionary
            if keyValue in valueDict:
                
                updateRow[2] = valueDict[keyValue][0] / updateRow[1]
               # add agencies list to feature as string
                updateRow[3] = str(valueDict[keyValue][1])
                # set relative percent for each agencies public land
                NumAgcys = len(valueDict[keyValue][2])
                for i in range(NumAgcys):
                    valueDict[keyValue][2][i] = valueDict[keyValue][2][i] / updateRow[1]
                #add list of relative percent coverage as string
                updateRow[4] = str(valueDict[keyValue][2])
            #otherwise set public land to 0
            else:
                updateRow[2] = 0
            #update feature
            updateRows.updateRow(updateRow)
    #delete value dictionary and subset specific public lands to save space
    del valueDict
    arcpy.management.Delete(Lands)
    return None
def MergeResults(subsets, filename, dirname, merging):
    '''
    Combines all subsets into a single file and then copies the file to create
    a results file  
    
    Inputs: sites subset or list of sites subset(if multiple subsets exist)
    
    Output: copy of merged subsets for use in results
    '''  
    suffix = "withPL"
    if merging:
        suffix = ""
    filelocation = dirname + "\\" + filename + suffix
    if len(subsets) == 1:   
        arcpy.management.CopyFeatures(subsets[0],filelocation)
    else:
        arcpy.management.Merge(subsets,filelocation)
    for file in subsets:
        arcpy.management.Delete(file)   
    return filelocation

def GroupHighPctSites(results, dirname, percent):
    '''
    Creates a seperate results feature class containing only sites with a given 
    percentage of public land. Majority landowning agency name and percent ownership
    is also included. 
        
    Inputs: Results file
        
    Output: None
    '''  
    for i in results:
        fileName = basename(i) 
        filelocation = dirname + "\\" + fileName + "above" + "pct"
        
        expr = "PctPL > " + str(percent)
        selectedsites = arcpy.management.SelectLayerByAttribute(i, "NEW_SELECTION", expr)
        arcpy.management.CopyFeatures(selectedsites, filelocation)
        updateFieldsList = ["Agencies","AgcyPct","MajorityAgcy","MajAgcyPct"]
        
        arcpy.management.AddField(
        in_table=filelocation,
        field_name=f"MajorityAgcy",
        field_type="Text",
        field_precision=None,
        field_scale=None,
        field_length=None,
        field_alias=f"MajorityAgcy",
        field_is_nullable="NULLABLE",
        field_is_required="NON_REQUIRED",
        field_domain=""
        )
        arcpy.management.AddField(
        in_table=filelocation,
        field_name=f"MajAgcyPct",
        field_type= "FLOAT",
        field_precision=None,
        field_scale=None,
        field_length=None,
        field_alias=f"MajAgcyPct",
        field_is_nullable="NULLABLE",
        field_is_required="NON_REQUIRED",
        field_domain=""
        )
        with arcpy.da.UpdateCursor(filelocation, updateFieldsList) as updateRows:
            for updateRow in updateRows:
                if updateRow[0] != None:
                    agcylist = literal_eval(updateRow[0])
                    pctlist = literal_eval(updateRow[1])
                    updateRow[2] = agcylist[0]
                    updateRow[3] = pctlist[0]
                    updateRows.updateRow(updateRow)    
    return None