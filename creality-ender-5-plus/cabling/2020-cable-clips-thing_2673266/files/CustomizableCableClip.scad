// Profile Type
profile_type = 2020; // [2020,3030]

// Inner Size of Cable Clip (will be scaled up if necessary)
inner_size = 8;

// Wall Thickness
wall_thickness = 1.5;

// Heigth
heigth = 7;

// Center Offset
center_offset = 0;

/* [Hidden] */
$fn=1000;

module profileConnector2020(heigth=10) {
    HEIGTH = heigth;
    %difference() {
        cube([20,20,1],center=true);
        cube([6.3,30,2],center=true);
        cube([30,6.3,2],center=true);
    }
    difference() {
        union() {
            translate([0,11,0])cube([13,1.5,HEIGTH],center=true);
            translate([0,9,0])cube([7,6,HEIGTH],center=true);
            hull() {
                translate([0,8,0])cube([11,0.1,HEIGTH],center=true);
                translate([0,6,0])cube([8,0.1,HEIGTH],center=true);
            }
        }
        translate([0,9,0])cube([4,6.2,HEIGTH+1],center=true);
    }
}

module profileConnector3030(heigth=10) {
    HEIGTH = heigth;
    %difference() {
        cube([30,30,1],center=true);
        cube([8.1,40,2],center=true);
        cube([40,8.1,2],center=true);
    }
    difference() {
        union() {
            translate([0,16,0])cube([17,2,HEIGTH],center=true);
            translate([0,13,0])cube([9,5,HEIGTH],center=true);
            hull() {
                translate([0,12,0])cube([13,0.1,HEIGTH],center=true);
                translate([0,10.5,0])cube([11,0.1,HEIGTH],center=true);
            }
        }
        translate([0,13,0])cube([6,10,HEIGTH+1],center=true);
    }
}

function offset(type) = 
            (type==2020) ? 12 :
            (type==3030) ? 17 : undef;

function clearance(type) =
            (type==2020) ? 4 :
            (type==3030) ? 6 : undef;

function real_center_offset(type,center_offset,size) =
            (type==2020) ? min(center_offset,size/2-2) :
            (type==3030) ? min(center_offset,size/2-3) : undef;

module connector(type, heigth) {
    if (type==2020) 
        profileConnector2020(heigth=heigth);
    else if (type==3030)
        profileConnector3030(heigth=heigth);
}
    

module cableClip(type=2020,wall=1.5,innerSize=10,heigth=5,center_offset=0) {
    SIZE=innerSize<clearance(type)?clearance(type):innerSize;
    WALLTHICKNESS=wall;
    HEIGTH=heigth;
    //offset&checks for 2020
    OFFSET=offset(type)+SIZE/2+(WALLTHICKNESS-2);
    //
    difference() {
        union() {
            connector(type,HEIGTH);
            translate([real_center_offset(type,center_offset,SIZE),0,0])translate([0,OFFSET,0])cylinder(d=SIZE+2*WALLTHICKNESS,h=HEIGTH,center=true);
            translate([-1*sign(center_offset)*(clearance(type)/2+WALLTHICKNESS/2),OFFSET-SIZE/4-WALLTHICKNESS/2,0])cube([WALLTHICKNESS,(SIZE+WALLTHICKNESS)/2,HEIGTH],center=true);
        }
        translate([real_center_offset(type,center_offset,SIZE),0,0])translate([0,OFFSET,0])cylinder(d=SIZE,h=HEIGTH+1,center=true);
        translate([0,OFFSET-SIZE/2,0])cube([clearance(type),SIZE,HEIGTH+1],center=true);
    }
}

cableClip(type=profile_type,wall=wall_thickness,innerSize=inner_size, heigth=heigth,center_offset=center_offset);

//cableClip(type=2020, wall=1.5, innerSize=5);
//cableClip(type=2020, wall=1.5, innerSize=7);
//cableClip(type=2020, wall=1.5, innerSize=10);
//cableClip(type=2020, wall=1.5, innerSize=15);
//cableClip(type=2020, wall=1.5, innerSize=20);
//cableClip(type=2020, wall=1.5, innerSize=20, heigth=10, center_offset=5);
//cableClip(type=2020, wall=1.5, innerSize=25, heigth=10);
//cableClip(type=2020, wall=1.5, innerSize=25, heigth=10,center_offset=5);

//cableClip(type=3030, wall=1.5, innerSize=7);
//cableClip(type=3030, wall=1.5, innerSize=10);
//cableClip(type=3030, wall=1.5, innerSize=15);
//cableClip(type=3030, wall=1.5, innerSize=25, heigth=10);
//cableClip(type=3030, wall=1.5, innerSize=30, heigth=10);
//cableClip(type=3030, wall=1.5, innerSize=35, heigth=10);
//cableClip(type=3030, wall=1.5, innerSize=35, heigth=10,center_offset=5);
