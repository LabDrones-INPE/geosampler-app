# Copyright (C) 2026 LABDRONES/INPE.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/gpl-3.0.html>.
#
"""Graphical User Interface (GUI) application for sample collection using Draw Folium plugin and drone images

   The image projection is based on EXIF/XMP metadata tags information and auxiliaries information such as flight height and dimension of sensor"""

# --------------------------
#        Imports
# --------------------------
from PIL import Image, ExifTags
import geopandas as gpd
#from osgeo import osr, gdal
from matplotlib import image
from affine import Affine  # For easy manipulation of affine matrix
from geopy import distance, Point
from shapely.geometry import Point as shply_Point
import os
from folium.raster_layers import ImageOverlay
from folium import Map, TileLayer, LayerControl
from folium.utilities import temp_html_filepath
from my_custom_folium_draw import Draw
import webbrowser
import numpy as np
from contextlib import contextmanager
import time


# --------------------------
#        Functions
# --------------------------
# Handle with Pyinstaller issue 4835
@contextmanager
def restore_lib_path():
    lib_key = "LD_LIBRARY_PATH"
    if (curr_env := os.environ.get(lib_key)) is not None:
        if (orig_env := os.environ.get(f"{lib_key}_ORIG")) is None:
            os.environ.pop(lib_key)
        else:
            os.environ[lib_key] = orig_env
    yield
    if curr_env is not None:
        os.environ[lib_key] = curr_env


def get_download_path():
    """Returns the default downloads path for linux or windows"""
    if os.name == 'nt':
        import winreg
        sub_key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        downloads_guid = "{374DE290-123F-4565-9164-39C4925E467B}"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            location = winreg.QueryValueEx(key, downloads_guid)[0]
        return location
    else:
        return os.path.join(os.path.expanduser('~'),'Downloads')
    
    
def decimal_coords(coords, ref):
    decimal_degrees = coords[0] + (float(coords[1]) / 60) + (float(coords[2]) / 3600)
    if ref == "S" or ref == "W":
        decimal_degrees = -decimal_degrees
    return decimal_degrees


# Features - https://www.dji.com/br/phantom-3-adv
# The sensor is 6.16mm wide and 4.62mm high. The maximum created still image size is 4000 pixels wide by 3000 tall - https://forum.dji.com/forum.php?mod=redirect&goto=findpost&ptid=28597&pid=197705
# Pixel size at sensor (Square): 1.562 micrometer
# Sensor size at X (TSX): 6.248 mm
# Sensor size at Y (TSY): 4.686 mm

# Features - https://sdk-forum.dji.net/hc/en-us/articles/12325496609689-What-is-the-custom-camera-parameters-for-Mavic-3-Enterprise-series-and-Mavic-3M
# The device have 4 cameras (RGB) and Multispectral(G, Red, Red Edge and Near Infrared)
# Image size	5280x3956 (RGB)	2592x1944 (MS)
# Sensor size at X (TSX): 17.4mm (RGB) 5.2mm (MS)
# Sensor size at Y (TSY): 13mm (RGB) 3.9mm (MS)

def get_exif_info(img_path):
    img = Image.open(img_path)
    if img._getexif() != None:
        exif = {ExifTags.TAGS[k]: v for k, v in img._getexif().items() if k in ExifTags.TAGS}
       
        try:
            coordenadas = exif['GPSInfo']
            altitude =  coordenadas[6]
            lat = decimal_coords(coordenadas[2], coordenadas[1])
            lon = decimal_coords(coordenadas[4], coordenadas[3])
            
        except KeyError:
            print('No Coordinates')            
    else:
        print('The image has no EXIF information:\n'+img_path)
        return None

    return {'focal_lenght':float(exif['FocalLength']),'date':str(exif['DateTime']),'img_dim_x':int(exif['ExifImageWidth']),'img_dim_y':int(exif['ExifImageHeight']),'center_coords':(float(lat),float(lon)),'altitude':float(altitude)}


def get_xmp_info(img_path):
    img = Image.open(img_path)
    xmp_info = img.getxmp()
    if xmp_info != None:
        try:
            flight_yaw_degree = xmp_info['xmpmeta']['RDF']['Description']['FlightYawDegree']            
        except KeyError:
            print('Flight Yaw Degree information not available!')       
    else:
        print('The image does not have XPM metadata information:\n'+img_path)
        return None
    return {'flight_yaw_degree':float(flight_yaw_degree)}


def create_cardinal_points(lat1, lon1, x_size, y_size, GSD, crs_src='EPSG:4326', crs_dst='EPSG:3395'):
    
    """This function create cardinal points coordinates based on center image coordinates,
       bering angle and distance. These points are used to determine upper-left corner coordinates
       of image and write Geotransform array in GDAL format and finally use Affine transformation
       to rotate and project drone images
       
       x_size - columns of image array
       y_size - rows of image array
       GSD - ground sample distance (cm)"""    
    
    #bearing (float) – Bearing in degrees: 0 – North, 90 – East, 180 – South, 270 or -90 – West.
    cardinal_bering = [0.,90.,180.,270.]
    d_meters = [(GSD * y_size/2.)/100.,(GSD * x_size/2.)/100.,(GSD * y_size/2.)/100.,(GSD * x_size/2.)/100.]

    origin = Point(lat1, lon1)
    drone_points = []
    for i,b in enumerate(cardinal_bering):
            # The geodesic distance is the shortest distance on the surface of an ellipsoidal model of the Earth.  
            # The default algorithm uses the method is given by 
            # `Karney (2013) <https://doi.org/10.1007%2Fs00190-012-0578-z>`_ (:class:`.geodesic`);
            # this is accurate to round-off and always converges.
            destination = distance.geodesic(meters=d_meters[i]).destination(origin, bearing=b)
            drone_points.append(shply_Point([destination.longitude,destination.latitude])) #x, y, z : float Easting, northing, and elevation)

    # Set up transformers, EPSG:3395 is metric
    gdf_cardinal_points = gpd.GeoDataFrame({'geometry':drone_points}, geometry='geometry', crs=crs_src)
    gdf_cardinal_points = gdf_cardinal_points.to_crs(crs_dst)
    
    return gdf_cardinal_points


# Some functions declaration for clarify the code
# Adapted from https://gis.stackexchange.com/a/408396
def rotate_gt(affine_matrix, angle, pivot=None):
    """This function generate a rotated affine matrix
    """

    # The gdal affine matrix format is not the same
    # of the Affine format, so we use a bullit-in function
    # to change it
    # see : https://github.com/sgillies/affine/blob/master/affine/__init__.py#L178
    affine_src = Affine.from_gdal(*affine_matrix)
    # We made the rotation. For this we calculate a rotation matrix,
    # with the rotation method and we combine it with the original affine matrix
    # Be careful, the star operator (*) is surcharged by Affine package. He make
    # a matrix multiplication, not a basic multiplication
    affine_dst = affine_src * affine_src.rotation(angle, pivot)
    # We return the rotated matrix in gdal format
    return affine_dst.to_gdal()


def create_rotated_img(file_in,flight_yaw_degre):    
    """
    Creates rotated numpy array from raw images (JPG) of RPAs

       :param file_in: raw image (JPG)
       :type file_in: String

       :param flight_yaw_degree: angle in degrees related to North from North-East-Down (NED) coordinates, counterclockwise for negative or clockwise for positive values.
       :type arr: Float
    """

    input_image = Image.open(file_in).convert("RGBA")
    #rotate image
    rot = input_image.rotate( (-flight_yaw_degre) % 360, resample=Image.NEAREST, expand=True, fillcolor=(255,255,255))
    
    #change white background to transparent
    img = np.array(rot)    
    img_final = img.copy()
    img_final[(img[...,0] == 255) & (img[...,1] == 255) & (img[...,2] == 255),3] = 0
        
    return img_final


def create_map(rpa_image,flight_info):
    # Use WGS 84 (EPSG:4326) as the geographic coordinate system
    crs_dst = 'EPSG:4326'

    exif_info = get_exif_info(rpa_image)
    xmp_info = get_xmp_info(rpa_image)
    if exif_info != None and xmp_info != None:    
        #Ground Sample Distance (cm) based on flying height above ground level, sensor width size (mm), focal lenght (mm), image width (pixels)
        GSD = (flight_info['flight_height_m']  * flight_info['sensor_width_mm']) / (exif_info['img_dim_x'] * exif_info['focal_lenght']) * 100.0
        
        # Get corner coordinates of image based on center coordinates, spatial resolution and dimensions of image:    
        gdf_cardinal_points = create_cardinal_points(exif_info['center_coords'][0], exif_info['center_coords'][1], 
                                                exif_info['img_dim_x'], exif_info['img_dim_y'], GSD,
                                                crs_src='EPSG:4326', #coordinate reference system of lat/lon
                                                crs_dst=crs_dst)

    x1,y1,x2,y2 = gdf_cardinal_points.total_bounds
    p_size_x = abs(x1-x2)/exif_info['img_dim_x']
    p_size_y = abs(y1-y2)/exif_info['img_dim_y']

    # Defining Affine parameters to get GeoTransform rotaded and calc bounding box limits:

    #In case of north up images, the GT(2) and GT(4) coefficients are zero, and the GT(1) is pixel width, and GT(5) is pixel height. 
    #The (GT(0),GT(3)) position is the top left corner of the top left pixel of the raster.
    gt_affine = (x1, p_size_x, 0, y2, 0, -p_size_y)

    # Now we can rotate the raster
    # Adapted from https://gis.stackexchange.com/a/408396

    # get the center of the raster to set the rotation center
    # Be carefull, the center is in pixel number, not in projected coordinates
    center = ((exif_info['img_dim_x'] / 2), (exif_info['img_dim_y'] / 2))

    # rotate the destination raster, with setting a new affine matrix made by the "rotate_gt" function.
    # gt_affine is the initial affine matrix. Array is 'North up' reference, but image
    # is rotaded using Flight Yaw degree  basead on the center of raster
    gt = rotate_gt(gt_affine, xmp_info['flight_yaw_degree'], center)

    # Formula to get an Image's Bounding Box from it's GDAL GeoTransform Array - https://gis.stackexchange.com/a/291642
    #Upper Left
    x_ul = gt[0] 
    y_ul = gt[3]

    #Lower Left
    x_ll = gt[0] + exif_info['img_dim_y']*gt[2]
    y_ll = gt[3] + exif_info['img_dim_y']*gt[5]

    #Upper Right
    x_ur = gt[0] + exif_info['img_dim_x']*gt[1]
    y_ur = gt[3] + exif_info['img_dim_x']*gt[4]

    #Lower Right
    x_lr = gt[0] + exif_info['img_dim_x']*gt[1] + exif_info['img_dim_y']*gt[2]
    y_lr = gt[3] + exif_info['img_dim_y']*gt[5] + exif_info['img_dim_x']*gt[4]

    min_lat = min(y_ul,y_ll,y_ur,y_lr)
    max_lat = max(y_ul,y_ll,y_ur,y_lr)
    min_lon = min(x_ul,x_ll,x_ur,x_lr)
    max_lon = max(x_ul,x_ll,x_ur,x_lr)

    # Define bounding box for image overlay:
    bounds_fin = [[min_lat, min_lon], [max_lat, max_lon]]
    
    # Get center coordinates:
    centre_lon = bounds_fin[0][1] + (bounds_fin[1][1] - bounds_fin[0][1])/2
    centre_lat = bounds_fin[0][0] + (bounds_fin[1][0] - bounds_fin[0][0])/2

    # Define a Folium map:
    m = Map(location=[centre_lat, centre_lon], tiles = None,
                        zoom_start = 18, max_zoom = 100, control_scale=True, zoom_control=False)
    
    # Save file with samples:
    f_out_geojson = os.path.splitext(os.path.basename(rpa_image))[0] + '_samples.geojson'

    Draw(export=True,
        filename=f_out_geojson,
        position="topleft",
        show_geometry_on_click = False,
        draw_options={
            "polyline": False,
            "circle": False,
            "marker": False}
    ).add_to(m)

    # Load tile layers:
    # OpenStreetMap
    TileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            name='OpenStreetMap', max_zoom = 100).add_to(m)

    # World Imagery basemap (ESRI)
    TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', 
                    attr='ArcGIS.World_Imagery', name='ArcGIS World', max_zoom = 100).add_to(m)

    # Load RPA image projected:
    img = create_rotated_img(rpa_image,xmp_info['flight_yaw_degree'])            
    m.add_child(ImageOverlay(img, opacity=1.0, bounds = bounds_fin, name=os.path.splitext(os.path.basename(rpa_image))[0]))

    LayerControl(collapsed=False).add_to(m)

    # Display the Map in the default web browser:
    with temp_html_filepath(m.get_root().render()) as fname:
        with restore_lib_path():
                webbrowser.open(fname)
                time.sleep(5) #delay needed to load HTML before removing the temporary file

    return f_out_geojson



#rpa_image='/home/user/Desktop/HARMONIZE-Br_Project/src/FieldWorkCampaigns/Cameta2019/Ani5_20190929/NADIR_Images/DJI_0947.JPG'
#flight_info = {'flight_height_m':150,'course_angle_degrees':35,'sensor_width_mm':6.248}
#create_map(rpa_image,flight_info)


    
